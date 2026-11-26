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

    payment_type = (
        Order.PAYMENT_CASH
        if str(data.get("payment_type") or "").lower() == "cash"
        else Order.PAYMENT_ROZETKA
    )

    purchases = list(data.get("purchases") or [])
    matched, notes = _merge_lines(purchases)

    note_lines = [f"Rozetka №{rozetka_id}"]
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
    """One poll. Returns {"created": n, "skipped": n, "errors": [...], "disabled": bool}.

    Never raises.
    """
    from order.models import Order

    from .models import RozetkaSettings

    summary = {"created": 0, "skipped": 0, "errors": [], "disabled": False}
    close_old_connections()
    settings = None
    try:
        settings = RozetkaSettings.load()
        if not settings.is_configured:
            summary["disabled"] = True
            return summary

        client = client or RozetkaClient(settings)
        since = (timezone.localtime() - timedelta(days=lookback_days)).date()
        for data in client.iter_orders(created_from=since):
            try:
                if int(data.get("status_group") or 0) == STATUS_GROUP_FAILED:
                    summary["skipped"] += 1
                    continue
                if Order.objects.filter(rozetka_order_id=int(data["id"])).exists():
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
