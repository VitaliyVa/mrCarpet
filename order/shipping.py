"""After the rug leaves: the TTN, the «відправлено» letter, Nova Poshta tracking.

* normalize_ttn / tracking_url: what the bot accepts and links to.
* enqueue_shipped_email: «Ваш килим уже в дорозі, ТТН ...», once per order,
  only to real addresses of site orders (Rozetka tells its buyers itself).
* shipped_messenger_text: the same news as a text to forward when there is no
  email.
* track_shipments: asks Nova Poshta about every shipped site order and tells
  the shop chat when the parcel arrives, waits too long, is refused, or is
  picked up (then the order becomes «Виконано» by itself).

Nova Poshta also notifies the recipient by its own SMS / app message when the
waybill is created and when the parcel arrives, so the TTN letter is a
courtesy, not the only channel.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.db import close_old_connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

TTN_RE = re.compile(r"^\d{14}$")
TRACK_EVERY = timedelta(hours=2)
REMIND_AFTER = timedelta(days=3)
NP_BATCH = 100

# Nova Poshta TrackingDocument.getStatusDocuments StatusCode groups.
NP_ARRIVED = {"7", "8"}
NP_RECEIVED = {"9", "10", "11", "106"}
NP_REFUSED = {"102", "103", "108"}
NP_STORAGE_STOPPED = {"105"}
NP_FAILED_DELIVERY = {"111"}
NP_NOT_FOUND = {"3"}
NP_DELETED = {"2"}


def normalize_ttn(raw: str | None) -> str:
    """'20 4500 1234 5678' -> '20450012345678'; '' when it is not a TTN."""
    digits = re.sub(r"\D", "", raw or "")
    return digits if TTN_RE.match(digits) else ""


def tracking_url(ttn: str) -> str:
    return f"https://novaposhta.ua/tracking/?cargo_number={ttn}"


def _delivery(order) -> str:
    from order.customer_contact import _delivery_text

    return _delivery_text(order)


def _payment(order) -> str:
    from order.models import Order

    total = f"{float(order.total_price or 0):.0f} грн"
    if order.payment_type == Order.PAYMENT_CASH:
        return f"при отриманні, {total}"
    if order.payment_type == Order.PAYMENT_PREPAY:
        return f"передоплата, {total}"
    return f"оплачено, {total}"


def has_real_email(order) -> bool:
    email = (order.email or "").strip()
    return bool(email) and not email.lower().endswith("@temp.com")


# ------------------------------------------------------------ the letter ---


def build_shipped_email(order) -> tuple[str, str, str]:
    from project.email_branding import render_branded_email, with_plain_footer
    from project.seo_jsonld import ORG_PHONE

    name = (order.name or "").strip()
    number = order.order_number or order.pk
    ttn = order.ttn.strip()
    delivery = _delivery(order)
    payment = _payment(order)
    url = tracking_url(ttn)
    phone = f"+{ORG_PHONE.lstrip('+')}"
    subject = f"mr.Carpet: замовлення №{number} вже в дорозі"
    body = with_plain_footer(
        (f"{name}, ваш" if name else "Ваш") + " килим уже в дорозі.\n\n"
        f"Ми відправили замовлення №{number} Новою Поштою.\n"
        f"Номер накладної (ТТН): {ttn}\n"
        + (f"Куди: Нова Пошта, {delivery}\n" if delivery else "")
        + f"Оплата: {payment}\n\n"
        f"Відстежити посилку: {url}\n\n"
        "Коли посилка прибуде у відділення, Нова Пошта вас повідомить.\n"
        f"Якщо є питання, відповідайте на цей лист або дзвоніть {phone}.\n\n"
        "mr.Carpet"
    )
    html = render_branded_email(
        "emails/order_shipped.html",
        {
            "name": name,
            "order_number": number,
            "ttn": ttn,
            "delivery": delivery,
            "payment": payment,
            "tracking_url": url,
            "shop_phone": phone,
        },
        eyebrow="Замовлення відправлено",
        preheader=f"ТТН {ttn}",
    )
    return subject, body, html


def send_shipped_email(order_pk: int) -> bool:
    """Send now (thread / tests). Marks the order only when the letter left."""
    from order.models import Order
    from project.smtp_utils import send_smtp_mail

    order = Order.objects.filter(pk=order_pk).first()
    if (
        order is None
        or order.shipped_email_sent_at
        or order.source != Order.SOURCE_SITE
        or not has_real_email(order)
        or not (order.ttn or "").strip()
    ):
        return False
    subject, body, html = build_shipped_email(order)
    ok = send_smtp_mail(subject, body, [order.email.strip()], fail_silently=True, html_message=html)
    if ok:
        Order.objects.filter(pk=order.pk).update(shipped_email_sent_at=timezone.now())
    return bool(ok)


def enqueue_shipped_email(order_pk: int) -> None:
    import threading

    def _run():
        close_old_connections()
        try:
            send_shipped_email(order_pk)
        except Exception:
            logger.exception("shipped email failed for order %s", order_pk)
        finally:
            close_old_connections()

    transaction.on_commit(
        lambda: threading.Thread(target=_run, daemon=True, name="order-shipped-email").start()
    )


def shipped_messenger_text(order) -> str:
    name = (order.name or "").strip()
    ttn = (order.ttn or "").strip()
    lines = [
        f"Добрий день, {name}!" if name else "Добрий день!",
        f"Ваш килим уже в дорозі 🚚 Замовлення №{order.order_number or order.pk}.",
        f"Номер накладної Нової Пошти: {ttn}",
        f"Відстежити: {tracking_url(ttn)}",
        "Коли посилка прибуде у відділення, Нова Пошта вас повідомить.",
        "Дякуємо, що обрали mr.Carpet!",
    ]
    return "\n".join(lines)


def pickup_reminder_text(order) -> str:
    name = (order.name or "").strip()
    delivery = _delivery(order)
    return "\n".join(
        [
            f"Добрий день, {name}!" if name else "Добрий день!",
            "Це mr.Carpet. Ваш килим уже чекає у відділенні Нової Пошти"
            + (f": {delivery}." if delivery else "."),
            f"Номер накладної: {(order.ttn or '').strip()}",
            "Заберіть, будь ласка, коли буде зручно, бо посилка зберігається недовго.",
            "Якщо щось змінилось, напишіть нам, ми допоможемо.",
        ]
    )


# ------------------------------------------------------------- tracking ---


def _notified(order) -> set:
    return {k for k in (order.np_notified or "").split(",") if k}


def _np_status(documents: list[dict]) -> list[dict]:
    from nova_poshta.utils import get_response

    response = get_response(
        "TrackingDocument", "getStatusDocuments", {"Documents": documents}, max_retries=2
    )
    return list(response.get("data") or [])


def _send(text: str, order) -> None:
    from order.customer_contact import order_keyboard
    from project.telegram_utils import _should_notify, send_telegram_message

    if not _should_notify("order"):
        return
    send_telegram_message(text, parse_mode="HTML", reply_markup=order_keyboard(order))


def _esc(value) -> str:
    import html

    return html.escape(str(value or ""), quote=False)


def _head(order) -> str:
    from project.telegram_utils import order_admin_absolute_url

    name = f"{order.name or ''} {order.surname or ''}".strip() or "покупець"
    return (
        f'№{_esc(order.order_number or order.pk)} · {_esc(name)}, {_esc(order.phone or "—")}\n'
        f'ТТН {_esc(order.ttn)} · <a href="{_esc(order_admin_absolute_url(order))}">адмінка</a>'
    )


def _handle(order, row: dict, now) -> list[str]:
    """Apply one Nova Poshta status row. Returns event keys it reported."""
    from order.models import Order

    code = str(row.get("StatusCode") or "").strip()
    status = str(row.get("Status") or "").strip()[:255]
    seen = _notified(order)
    events: list[str] = []
    fields = {"np_status_code": code, "np_status": status, "np_checked_at": now}

    if code in NP_ARRIVED:
        arrived = order.np_arrived_at or now
        fields["np_arrived_at"] = arrived
        if "arrived" not in seen:
            events.append("arrived")
            _send(f"📦 Посилка прибула у відділення\n{_head(order)}\n"
                  "Нова Пошта вже повідомила покупця.", order)
        elif "remind" not in seen and now - arrived >= REMIND_AFTER:
            events.append("remind")
            _send(
                f"⏰ Посилку не забирають вже {(now - arrived).days} дні\n{_head(order)}\n"
                "Варто нагадати покупцю. Текст:\n"
                f"<pre>{_esc(pickup_reminder_text(order))}</pre>",
                order,
            )
    elif code in NP_RECEIVED:
        if "received" not in seen:
            events.append("received")
        if order.status == Order.STATUS_SHIPPED:
            order.status = Order.STATUS_COMPLETED
            order.save()  # signals: completed_at, GA4 purchase for cash orders
            _send(
                f"✅ Покупець забрав посилку, статус «Виконано»\n{_head(order)}\n"
                "Через 10 днів попросимо відгук (лист або текст для Viber сюди).",
                order,
            )
    elif code in NP_REFUSED | NP_STORAGE_STOPPED | NP_FAILED_DELIVERY:
        key = f"problem{code}"
        if key not in seen:
            events.append(key)
            _send(
                f"⚠️ Проблема з посилкою: {_esc(status)}\n{_head(order)}\n"
                "Зателефонуйте покупцю. Якщо посилка повертається, після повернення "
                "поставте «Скасовано»: килим сам повернеться на склад.",
                order,
            )
    elif code in NP_NOT_FOUND | NP_DELETED:
        if "notfound" not in seen and order.updated and now - order.updated > timedelta(hours=12):
            events.append("notfound")
            _send(f"⚠️ Нова Пошта не знаходить ТТН ({_esc(status)})\n{_head(order)}\n"
                  "Перевірте номер накладної.", order)

    if events:
        fields["np_notified"] = ",".join(sorted(seen | set(events)))[:255]
    type(order).objects.filter(pk=order.pk).update(**fields)
    return events


def due_for_tracking(now=None):
    from django.db.models import Q

    from order.models import Order

    now = now or timezone.now()
    return (
        Order.objects.filter(status=Order.STATUS_SHIPPED, source=Order.SOURCE_SITE)
        .exclude(ttn="")
        .filter(Q(np_checked_at__isnull=True) | Q(np_checked_at__lte=now - TRACK_EVERY))
        .order_by("np_checked_at", "pk")
    )


def track_shipments(now=None, *, limit: int = 300) -> str:
    """One tracking pass. Never raises."""
    from order.customer_contact import normalize_phone

    now = now or timezone.now()
    try:
        orders = [o for o in due_for_tracking(now)[:limit] if normalize_ttn(o.ttn)]
    except Exception as exc:
        logger.exception("tracking query failed")
        return f"tracking failed: {exc}"
    if not orders:
        return "tracking: nothing to check"
    events = 0
    errors = 0
    for start in range(0, len(orders), NP_BATCH):
        chunk = orders[start:start + NP_BATCH]
        documents = [
            {"DocumentNumber": normalize_ttn(o.ttn), "Phone": normalize_phone(o.phone)}
            for o in chunk
        ]
        try:
            rows = _np_status(documents)
        except Exception:
            logger.exception("Nova Poshta tracking call failed")
            errors += len(chunk)
            continue
        by_ttn = {str(r.get("Number") or ""): r for r in rows}
        for order in chunk:
            row = by_ttn.get(normalize_ttn(order.ttn))
            if not row:
                continue
            try:
                events += len(_handle(order, row, now))
            except Exception:
                logger.exception("tracking update failed for order %s", order.pk)
                errors += 1
    return f"tracking: {len(orders)} checked, {events} events, {errors} errors"
