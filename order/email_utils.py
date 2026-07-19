import logging

from django.db import close_old_connections, transaction

from project.email_branding import render_branded_email, with_plain_footer
from project.smtp_utils import send_smtp_mail, send_smtp_mail_async

logger = logging.getLogger(__name__)


def delivery_parts(city: str | None, address: str | None) -> tuple[str, str]:
    """
    Split city vs Nova Poshta warehouse (stored in Order.address).
    When address duplicates city, warehouse is treated as missing.
    """
    city = (city or "").strip()
    address = (address or "").strip()
    if address and city and address.casefold() == city.casefold():
        return city, ""
    return city, address


def format_delivery_line(city: str | None, address: str | None) -> str:
    """
    Single-line delivery for plain text / Telegram.
    Prefer «Місто · Відділення»; avoid «Ланівці, Ланівці».
    """
    city_part, warehouse = delivery_parts(city, address)
    if not city_part and not warehouse:
        return "—"
    if not warehouse:
        return city_part or "—"
    if not city_part:
        return warehouse
    # warehouse already starts with city
    prefix = f"{city_part},"
    if warehouse.casefold().startswith(prefix.casefold()) or warehouse.casefold().startswith(
        f"{city_part} ".casefold()
    ):
        return warehouse
    return f"{city_part} · {warehouse}"


def _free_shipping_email_line(order) -> str:
    if not getattr(order, "free_shipping", False):
        return "за тарифами перевізника"
    threshold = getattr(order, "free_shipping_threshold", None)
    if threshold:
        return f"безкоштовно (від {threshold} грн)"
    return "безкоштовно"


def _build_order_email(order):
    payment_label = order.get_payment_type_display()
    status_label = order.get_status_display()
    price = f"{order.total_price:.0f} грн" if order.total_price is not None else "—"
    customer = f"{order.name} {order.surname}".strip()
    city_part, warehouse = delivery_parts(order.city, order.address)
    delivery = format_delivery_line(order.city, order.address)
    shipping_cost = _free_shipping_email_line(order)
    promocode_label = getattr(order, "promocode_label", "") or ""

    subject = f"mr.Carpet — замовлення №{order.order_number} прийнято"
    promo_plain = f"Промокод: {promocode_label}\n" if promocode_label else ""
    warehouse_plain = warehouse or "⚠️ не вказано"
    body = with_plain_footer(
        f"Дякуємо за замовлення!\n\n"
        f"Номер замовлення: {order.order_number}\n"
        f"Статус: {status_label}\n"
        f"Отримувач: {customer}\n"
        f"Телефон: {order.phone or '—'}\n"
        f"Місто: {city_part or '—'}\n"
        f"Відділення НП: {warehouse_plain}\n"
        f"Вартість доставки: {shipping_cost}\n"
        f"{promo_plain}"
        f"Спосіб оплати: {payment_label}\n"
        f"Сума: {price}\n\n"
        f"Ми зв’яжемося з вами для підтвердження деталей.\n\n"
        f"— mr.Carpet"
    )
    html = render_branded_email(
        "emails/order_confirmation.html",
        {
            "order_number": order.order_number,
            "status_label": status_label,
            "customer": customer,
            "phone": order.phone or "—",
            "city": city_part or "—",
            "warehouse": warehouse or "—",
            "delivery": delivery,
            "shipping_cost": shipping_cost,
            "free_shipping": bool(getattr(order, "free_shipping", False)),
            "promocode_label": promocode_label,
            "payment_label": payment_label,
            "price": price,
        },
        eyebrow="Підтвердження замовлення",
        preheader=f"Замовлення №{order.order_number} прийнято · {price}",
    )
    return subject, body, html


def send_order_confirmation_email(order):
    """Синхронна відправка (shell / тести)."""
    if not order.email or order.email.endswith("@temp.com"):
        msg = f"[order-email] skip: no real email for order #{order.pk}"
        logger.info(msg)
        print(msg)
        return False

    subject, body, html = _build_order_email(order)
    ok = send_smtp_mail(
        subject, body, [order.email], fail_silently=True, html_message=html
    )
    if ok:
        print(f"[order-email] sent OK → {order.email} (order #{order.order_number})")
    return ok


def enqueue_order_confirmation_email(order_id):
    """
    Після commit БД — ставить лист у фон.
    API одразу повертає 201, не чекаючи Gmail (як контактна форма + async).
    """

    def _after_commit():
        close_old_connections()
        try:
            from order.models import Order

            order = Order.objects.filter(pk=order_id).first()
            if not order:
                print(f"[order-email] skip: order #{order_id} not found")
                return
            if not order.email or order.email.endswith("@temp.com"):
                print(f"[order-email] skip: no real email for order #{order_id}")
                return

            subject, body, html = _build_order_email(order)
            send_smtp_mail_async(
                subject, body, [order.email], html_message=html
            )
            print(f"[order-email] queued → {order.email} (order #{order.order_number})")
        except Exception as exc:
            logger.exception("enqueue order email failed: %s", exc)
            print(f"[order-email] enqueue FAILED: {exc}")
        finally:
            close_old_connections()

    transaction.on_commit(_after_commit)
