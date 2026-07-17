import logging

from django.db import close_old_connections, transaction

from project.smtp_utils import send_smtp_mail, send_smtp_mail_async

logger = logging.getLogger(__name__)


def _build_order_email(order):
    payment_label = order.get_payment_type_display()
    status_label = order.get_status_display()
    price = f"{order.total_price:.0f} грн" if order.total_price is not None else "—"

    subject = f"mr.Carpet — замовлення №{order.order_number} прийнято"
    body = (
        f"Дякуємо за замовлення!\n\n"
        f"Номер замовлення: {order.order_number}\n"
        f"Статус: {status_label}\n"
        f"Отримувач: {order.name} {order.surname}\n"
        f"Телефон: {order.phone or '—'}\n"
        f"Місто: {order.city or '—'}\n"
        f"Адреса / відділення: {order.address or '—'}\n"
        f"Спосіб оплати: {payment_label}\n"
        f"Сума: {price}\n\n"
        f"Ми зв’яжемося з вами для підтвердження деталей.\n\n"
        f"— mr.Carpet"
    )
    return subject, body


def send_order_confirmation_email(order):
    """Синхронна відправка (shell / тести)."""
    if not order.email or order.email.endswith("@temp.com"):
        msg = f"[order-email] skip: no real email for order #{order.pk}"
        logger.info(msg)
        print(msg)
        return False

    subject, body = _build_order_email(order)
    ok = send_smtp_mail(subject, body, [order.email], fail_silently=True)
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

            subject, body = _build_order_email(order)
            # SMTP у daemon-thread — відповідь клієнту не блокується
            send_smtp_mail_async(subject, body, [order.email])
            print(f"[order-email] queued → {order.email} (order #{order.order_number})")
        except Exception as exc:
            logger.exception("enqueue order email failed: %s", exc)
            print(f"[order-email] enqueue FAILED: {exc}")
        finally:
            close_old_connections()

    transaction.on_commit(_after_commit)
