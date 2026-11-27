"""
Import of Rozetka Marketplace orders into our own Order table.

`import_new_orders()` is idempotent: Order.rozetka_order_id is unique, so a
Rozetka order that was already imported is never created twice, however often
the poller (manage.py rozetka_poll) looks at it. It never raises: any failure
lands in RozetkaSettings.last_error (visible in the admin) and in the log.

What an imported order is:
  * Order(source="rozetka", rozetka_order_id=<id>, order_number=<same id>, so
    the number in our admin and in Telegram equals the one in the Rozetka
    cabinet), status "new";
  * a Cart (ordered, no user) with one CartProduct per matched offer, which is
    how the rest of the code (admin, Telegram, emails) finds order items;
  * stock taken from ProductAttribute.quantity like the site checkout does
    (Cart.apply_quantity), and clamped at zero when Rozetka sold more than we
    had, with a note in the order message;
  * the same Telegram notification as a site order, headed «ROZETKA».
It deliberately sends no GA4 purchase and no ads conversion (those guard on
Order.source), and no customer email.

Cancellation: when Rozetka moves an imported order into status_group 3
(cancelled / failed, e.g. the buyer did not pick the parcel up), the poll marks
our Order "cancelled" and gives the stock back, exactly once: the status flip
and the stock change happen in one transaction under select_for_update, and an
order that is already "cancelled" (by an earlier poll or by a manager in the
admin) is never touched again. The admin itself returns no stock on cancel
(order/signals.py only releases the promo code), so there is no second path
that could restore it twice. Only what import took is returned: see
_stock_to_return for the oversold case.

Offer id: our Rozetka feed uses f"{product.pk}x{attr.pk}" (project/prom_feed.py
rozetka_offer_id) both as <offer id> and as <article>; the order carries it in
purchases[].item.uploader_offer_id / price_offer_id / article.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from .rozetka_api import (
    STATUS_GROUP_FAILED,
    RozetkaClient,
    RozetkaError,
)

logger = logging.getLogger(__name__)

# Orders created within this many days are looked at every poll. A window (not
# only "status = new") so an order the manager already moved on in the Rozetka
# cabinet before the next poll is still picked up.
LOOKBACK_DAYS = 3

# Cancellations of older orders (a parcel returned after a week) are found by a
# second, cheap search: failed orders (`types=6`, documented in /orders/search)
# whose status changed within this many days, whatever their creation date.
CANCEL_LOOKBACK_DAYS = 3
SEARCH_TYPES_FAILED = 6

OVERSOLD_NOTE_RE = re.compile(r"^Недостатньо залишку: «(.*)» замовлено (\d+), було (\d+)$")

OFFER_ID_RE = re.compile(r"^(\d+)x(\d+)$")
MESSAGE_MAX = 1024
ADDRESS_MAX = 512


def _dec(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _num(value) -> float | None:
    dec = _dec(value)
    return float(dec) if dec is not None else None


def normalize_phone(raw) -> str:
    """380954954374 / 0954954374 / +38 (095) 495-43-74 -> +380954954374."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return ""
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    return f"+{digits}"


def split_name(full_name: str) -> tuple[str, str]:
    """Rozetka gives «Прізвище Ім'я [По батькові]»; Order wants (name, surname).

    One word fills both, like the site checkout does.
    """
    parts = (full_name or "").split()
    if not parts:
        return "Покупець Rozetka", "Покупець Rozetka"
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[1], parts[0]


def _clean_email(raw) -> str:
    value = str(raw or "").strip()
    if not value or "@" not in value:
        return ""
    try:
        validate_email(value)
    except ValidationError:
        return ""
    return value[:254]


def delivery_text(delivery: dict, delivery_service: dict | None = None) -> tuple[str, str]:
    """(city, warehouse text) from the order's `delivery` block."""
    delivery = delivery or {}
    city = delivery.get("city") or {}
    city_name = (
        city.get("name_ua") or city.get("title") or city.get("name") or ""
    ).strip()
    service = (
        delivery.get("delivery_service_name")
        or (delivery_service or {}).get("name")
        or ""
    ).strip()
    pieces = []
    if service:
        pieces.append(service)
    number = str(delivery.get("place_number") or "").strip()
    if number:
        pieces.append(f"№{number}")
    street = str(delivery.get("place_street") or "").strip()
    house = str(delivery.get("place_house") or "").strip()
    flat = str(delivery.get("place_flat") or "").strip()
    address = ", ".join(p for p in (street, house) if p)
    if flat:
        address = f"{address}, кв. {flat}" if address else f"кв. {flat}"
    text = " ".join(pieces)
    if address:
        text = f"{text}, {address}" if text else address
    return city_name, text[:ADDRESS_MAX]


def offer_id_candidates(purchase: dict) -> list[str]:
    item = purchase.get("item") or {}
    values = [
        item.get("uploader_offer_id"),
        item.get("price_offer_id"),
        item.get("article"),
        purchase.get("offer_id"),
    ]
    return [str(v).strip() for v in values if v not in (None, "")]


def resolve_attribute(purchase: dict):
    """ProductAttribute for a Rozetka purchase line, or None when unknown."""
    from catalog.models import ProductAttribute

    for candidate in offer_id_candidates(purchase):
        match = OFFER_ID_RE.match(candidate)
        if not match:
            continue
        product_pk, attr_pk = int(match.group(1)), int(match.group(2))
        attr = (
            ProductAttribute.objects.select_related("product", "size")
            .filter(pk=attr_pk, product_id=product_pk)
            .first()
        )
        if attr is not None:
            return attr
    return None


def _unit_price(purchase: dict) -> float | None:
    for key in ("price_with_discount", "price"):
        value = _num(purchase.get(key))
        if value is not None:
            return value
    return None


def _order_total(data: dict, lines: list[dict]) -> float | None:
    """Items total as Rozetka sold it (after discounts, without delivery)."""
    for key in ("amount_with_discount", "amount"):
        value = _num(data.get(key))
        if value is not None:
            return value
    total = 0.0
    seen = False
    for purchase in lines:
        price = _unit_price(purchase)
        if price is not None:
            total += price * int(purchase.get("quantity") or 0)
            seen = True
    return total if seen else _num(data.get("cost_with_discount"))


def _take_stock(cart) -> list[str]:
    """Decrease ProductAttribute.quantity; never below zero. Returns notes."""
    from catalog.models import ProductAttribute

    try:
        with transaction.atomic():
            cart.apply_quantity()
        return []
    except ValidationError:
        pass  # Rozetka already sold it: take what is left, tell the owner
    notes = []
    for cart_product in cart.cart_products.select_related("product_attr__product"):
        if cart_product.product_attr.custom_attribute:
            continue
        attr = ProductAttribute.objects.select_for_update().get(pk=cart_product.product_attr_id)
        available = int(attr.quantity or 0)
        if cart_product.quantity > available:
            notes.append(
                f"Недостатньо залишку: «{attr.product.title}» "
                f"замовлено {cart_product.quantity}, було {available}"
            )
        attr.quantity = max(available - cart_product.quantity, 0)
        attr.save(update_fields=["quantity"])
    return notes


def _merge_lines(purchases: list[dict]):
    """({attr: qty}, unknown_notes) with the same attribute summed."""
    matched: dict = {}
    unknown = []
    for purchase in purchases:
        quantity = int(purchase.get("quantity") or 0)
        if quantity <= 0:
            continue
        attr = resolve_attribute(purchase)
        if attr is None:
            item = purchase.get("item") or {}
            name = purchase.get("item_name") or item.get("name") or "?"
            price = _unit_price(purchase)
            offer = (offer_id_candidates(purchase) or ["-"])[0]
            price_text = f", {price:.0f} грн" if price is not None else ""
            unknown.append(f"Не знайдено в каталозі: «{name}» × {quantity}{price_text} (offer {offer})")
            continue
        matched[attr] = matched.get(attr, 0) + quantity
    return matched, unknown


# payment_type_name words of the methods where the buyer pays the seller
# directly (card or bank account), not through Rozetka.
_PREPAY_WORDS = ("картку продавця", "рахунок продавця", "карту продавца", "счет продавца")


def _payment_name(data: dict) -> str:
    raw = data.get("payment_type_name")
    if isinstance(raw, dict):
        raw = raw.get("uk") or raw.get("ua") or raw.get("ru") or ""
    return str(raw or "").strip()[:200]


# status_payment names that mean the money is taken (hold = two-stage payment,
# blocked on the buyer's card until we confirm it in RozetkaPay).
_PAID_STATUSES = {"paid", "hold"}


def rozetka_paid(data: dict) -> bool:
    """True only when Rozetka says the online payment went through."""
    if data.get("is_payed") is True:
        return True
    status = data.get("status_payment") or {}
    if not isinstance(status, dict):
        return False
    return str(status.get("name") or "").lower() in _PAID_STATUSES


def order_payment_type(data: dict) -> str:
    """cash -> on delivery; paid to the seller directly -> prepay (manager must
    check the money); online through Rozetka (card, Apple/Google Pay, parts)
    -> rozetka when paid, rozetka_unpaid while the buyer has not paid yet
    (Rozetka sends these orders before the payment)."""
    from order.models import Order

    kind = str(data.get("payment_type") or "").lower()
    if kind == "cash":
        return Order.PAYMENT_CASH
    name = _payment_name(data).lower()
    if kind == "no_cash" or any(word in name for word in _PREPAY_WORDS):
        return Order.PAYMENT_PREPAY
    return Order.PAYMENT_ROZETKA if rozetka_paid(data) else Order.PAYMENT_ROZETKA_UNPAID


def mark_paid_if_needed(data: dict):
    """An imported order still waiting for its online payment: flip it to paid
    once Rozetka reports the money. Returns the order when it changed."""
    from order.models import Order

    if not rozetka_paid(data):
        return None
    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(
                rozetka_order_id=int(data["id"]),
                payment_type=Order.PAYMENT_ROZETKA_UNPAID,
            )
            .first()
        )
        if order is None:
            return None
        order.payment_type = Order.PAYMENT_ROZETKA
        line = "Rozetka: оплату отримано, можна відправляти"
        order.message = ((order.message + "\n") if order.message else "") + line
        order.message = order.message[:MESSAGE_MAX]
        order.save(update_fields=["payment_type", "message", "updated"])
    return order


def _notify_paid(order) -> None:
    try:
        from project import telegram_utils

        if not telegram_utils._should_notify("order"):
            return
        number = order.order_number or order.rozetka_order_id
        text = (
            f"ROZETKA 💳 Замовлення №{number} оплачено онлайн, можна відправляти\n"
            f"{telegram_utils.order_admin_absolute_url(order)}"
        )
        telegram_utils.send_telegram_message_async(text)
    except Exception:
        logger.exception("rozetka: telegram paid notify failed for order %s", order.pk)


def create_order(data: dict):
    """Create our Order from one Rozetka order dict. None if already imported.

    `data` must carry `purchases` (and ideally `delivery`, `user`).
    """
    from cart.models import Cart, CartProduct
    from order.models import Order

    rozetka_id = int(data["id"])
    if Order.objects.filter(rozetka_order_id=rozetka_id).exists():
        return None

    delivery = data.get("delivery") or {}
    user = data.get("user") or {}
    full_name = (
        delivery.get("recipient_title")
        or user.get("contact_fio")
        or (data.get("user_title") or {}).get("full_name")
        or ""
    )
    name, surname = split_name(str(full_name))
    buyer_phone = normalize_phone(data.get("user_phone"))
    phone = normalize_phone(delivery.get("recipient_phone")) or buyer_phone
    city, address = delivery_text(delivery, data.get("delivery_service"))

    payment_type = order_payment_type(data)
    payment_name = _payment_name(data)

    purchases = list(data.get("purchases") or [])
    matched, notes = _merge_lines(purchases)

    note_lines = [f"Rozetka №{rozetka_id}"]
    if payment_name:
        note_lines.append(f"Оплата: {payment_name}")
    comment = str(data.get("comment") or "").strip()
    if comment:
        note_lines.append(f"Коментар покупця: {comment}")
    if buyer_phone and buyer_phone != phone:
        note_lines.append(f"Телефон покупця: {buyer_phone}")
    if not purchases:
        notes.append("Rozetka не віддала список товарів, подивіться замовлення в кабінеті")

    try:
        with transaction.atomic():
            order = Order.objects.create(
                source=Order.SOURCE_ROZETKA,
                rozetka_order_id=rozetka_id,
                order_number=rozetka_id,
                status=Order.STATUS_NEW,
                name=name[:512],
                surname=surname[:512],
                email=_clean_email(user.get("email")),
                phone=phone[:512] or None,
                city=city[:255],
                address=address or None,
                total_price=_order_total(data, purchases),
                payment_type=payment_type,
                message=None,
            )
            cart = Cart.objects.create(user=None, ordered=True, order=order)
            for attr, quantity in matched.items():
                CartProduct.objects.create(cart=cart, product_attr=attr, quantity=quantity)
            stock_notes = _take_stock(cart) if matched else []
            all_notes = note_lines + notes + stock_notes
            order.message = "\n".join(all_notes)[:MESSAGE_MAX]
            order.save(update_fields=["message", "updated"])
    except IntegrityError:
        # Lost a race with another poller run: the winner owns the order.
        logger.info("rozetka: order %s was imported concurrently", rozetka_id)
        return None
    return order


def _stock_to_return(order, cart_products) -> dict:
    """{cart_product.pk: units to give back} for a cancelled imported order.

    Mirrors what import took. Custom (cut-to-length) lines are skipped: import
    creates them without a length, so neither Cart.apply_quantity nor the
    clamped fallback took anything for them (and saving a custom attribute
    would delete its cart lines, see ProductAttribute.save).

    Oversold lines: when Rozetka sold more than we had, import took only what
    was left and wrote «Недостатньо залишку: «title» замовлено N, було M» into
    order.message. Giving back N would create stock that never existed, so a
    line matched by (product title, ordered N) to such a note gets M back. Each
    note is used once, in cart order, which is the order import wrote them in.
    If a manager deleted that note, the full quantity is returned (documented
    trade-off: no model field records the taken amount).
    """
    notes = []
    for line in (order.message or "").splitlines():
        match = OVERSOLD_NOTE_RE.match(line.strip())
        if match:
            notes.append((match.group(1), int(match.group(2)), int(match.group(3))))
    result = {}
    for cart_product in cart_products:
        attr = cart_product.product_attr
        if attr.custom_attribute:
            continue
        quantity = int(cart_product.quantity or 0)
        for index, (title, ordered, available) in enumerate(notes):
            if title == attr.product.title and ordered == quantity:
                quantity = min(available, quantity)
                del notes[index]
                break
        if quantity > 0:
            result[cart_product.pk] = quantity
    return result


def cancel_order(rozetka_id: int):
    """Mark an imported order cancelled and return its stock. Exactly once.

    Returns (order, units_returned), or None when there is no such Rozetka
    order or it is already cancelled.
    """
    from cart.models import CartProduct
    from catalog.models import ProductAttribute
    from order.models import Order

    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(source=Order.SOURCE_ROZETKA, rozetka_order_id=int(rozetka_id))
            .first()
        )
        if order is None or order.status == Order.STATUS_CANCELLED:
            return None
        cart_products = list(
            CartProduct.objects.filter(cart__order=order)
            .select_related("product_attr__product")
            .order_by("pk")
        )
        to_return = _stock_to_return(order, cart_products)
        returned = 0
        for cart_product in cart_products:
            units = to_return.get(cart_product.pk)
            if not units:
                continue
            attr = ProductAttribute.objects.select_for_update().get(pk=cart_product.product_attr_id)
            attr.quantity = int(attr.quantity or 0) + units
            attr.save(update_fields=["quantity"])
            returned += units
        order.status = Order.STATUS_CANCELLED
        note = "Rozetka скасувала замовлення"
        if returned:
            note += ", залишок повернено"
        order.message = "\n".join(p for p in (order.message, note) if p)[:MESSAGE_MAX]
        order.save(update_fields=["status", "message", "updated"])
    return order, returned


def _notify_cancelled(order, returned: int) -> None:
    """Short plain Telegram line (notify_order has no cancel event)."""
    try:
        from project import telegram_utils

        if not telegram_utils._should_notify("order"):
            return
        number = order.order_number or order.rozetka_order_id
        tail = "залишок повернено" if returned else "залишок не змінювався"
        text = (
            f"ROZETKA ❌ Замовлення №{number} скасовано, {tail}\n"
            f"{telegram_utils.order_admin_absolute_url(order)}"
        )
        telegram_utils.send_telegram_message_async(text)
    except Exception:
        logger.exception("rozetka: telegram cancel notify failed for order %s", order.pk)


def _handle_failed(data: dict, summary: dict) -> None:
    """A status_group 3 order from Rozetka: cancel ours if we have one."""
    result = cancel_order(int(data["id"]))
    if result is None:
        summary["skipped"] += 1
        return
    order, returned = result
    summary["cancelled"] += 1
    _notify_cancelled(order, returned)


def _poll_late_cancellations(client, summary: dict, seen: set) -> None:
    """Orders older than the created_from window that Rozetka failed lately.

    Ids the main window already handled, unknown ids (never imported) and
    orders already cancelled here are passed over silently.
    """
    from order.models import Order

    since = (timezone.localtime() - timedelta(days=CANCEL_LOOKBACK_DAYS)).date()
    for data in client.iter_orders(
        types=SEARCH_TYPES_FAILED, status_updated_from=since.isoformat(), max_pages=5
    ):
        try:
            if int(data.get("status_group") or 0) != STATUS_GROUP_FAILED:
                continue
            rozetka_id = int(data["id"])
            if rozetka_id in seen:
                continue
            seen.add(rozetka_id)
            pending = (
                Order.objects.filter(source=Order.SOURCE_ROZETKA, rozetka_order_id=rozetka_id)
                .exclude(status=Order.STATUS_CANCELLED)
                .exists()
            )
            if pending:
                _handle_failed(data, summary)
        except Exception as exc:
            logger.exception("rozetka: cancellation of order %s failed", data.get("id"))
            summary["errors"].append(f"cancel {data.get('id')}: {exc}")


def _notify(order) -> None:
    """Same Telegram message as a site order (format_order_message adds ROZETKA)."""
    try:
        from project import telegram_utils

        telegram_utils.notify_order(order, event="new")
    except Exception:
        logger.exception("rozetka: telegram notify failed for order %s", order.pk)


def _record(settings_pk, *, error: str) -> None:
    from .models import RozetkaSettings

    try:
        RozetkaSettings.objects.filter(pk=settings_pk).update(
            last_poll_at=timezone.now(), last_error=error[:2000]
        )
    except Exception:
        logger.exception("rozetka: could not save poll status")


def import_new_orders(client: RozetkaClient | None = None, *, lookback_days: int = LOOKBACK_DAYS) -> dict:
    """One poll. Returns {"created", "cancelled", "skipped": n, "errors": [...], "disabled": bool}.

    Never raises.
    """
    from order.models import Order

    from .models import RozetkaSettings

    summary = {"created": 0, "cancelled": 0, "skipped": 0, "errors": [], "disabled": False}
    close_old_connections()
    settings = None
    try:
        settings = RozetkaSettings.load()
        if not settings.is_configured:
            summary["disabled"] = True
            return summary

        client = client or RozetkaClient(settings)
        since = (timezone.localtime() - timedelta(days=lookback_days)).date()
        seen: set[int] = set()
        for data in client.iter_orders(created_from=since):
            try:
                seen.add(int(data["id"]))
                if int(data.get("status_group") or 0) == STATUS_GROUP_FAILED:
                    _handle_failed(data, summary)
                    continue
                if Order.objects.filter(rozetka_order_id=int(data["id"])).exists():
                    paid = mark_paid_if_needed(data)
                    if paid is not None:
                        summary["paid"] = summary.get("paid", 0) + 1
                        _notify_paid(paid)
                    else:
                        summary["skipped"] += 1
                    continue
                if "purchases" not in data:
                    data = client.get_order(int(data["id"]))
                order = create_order(data)
                if order is None:
                    summary["skipped"] += 1
                    continue
                summary["created"] += 1
                _notify(order)
            except RozetkaError as exc:
                summary["errors"].append(str(exc))
            except Exception as exc:
                logger.exception("rozetka: order %s import failed", data.get("id"))
                summary["errors"].append(f"order {data.get('id')}: {exc}")
        _poll_late_cancellations(client, summary, seen)
    except RozetkaError as exc:
        summary["errors"].append(str(exc))
    except Exception as exc:
        logger.exception("rozetka: poll failed")
        summary["errors"].append(f"poll failed: {exc}")
    finally:
        if settings is not None and not summary["disabled"]:
            _record(settings.pk, error="; ".join(summary["errors"][:3]))
        close_old_connections()
    if summary["errors"]:
        logger.warning("rozetka poll errors: %s", summary["errors"])
    return summary
