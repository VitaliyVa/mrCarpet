import logging

from django.core.mail import get_connection, send_mail

from project.models import SMTPSettings

logger = logging.getLogger(__name__)


def send_order_confirmation_email(order):
    """Надсилає клієнту лист про успішне оформлення замовлення."""
    if not order.email or order.email.endswith("@temp.com"):
        msg = f"[order-email] skip: no real email for order #{order.pk}"
        logger.info(msg)
        print(msg)
        return False

    try:
        smtp = SMTPSettings.load()
        if not smtp.host or not smtp.server_email or not smtp.email_host_password:
            msg = "[order-email] skip: SMTPSettings incomplete (host/email/password)"
            logger.warning(msg)
            print(msg)
            return False

        # Gmail App Password часто копіюють з пробілами — прибираємо
        password = (smtp.email_host_password or "").replace(" ", "").strip()
        username = (smtp.username or smtp.server_email or "").strip()

        connection = get_connection(
            host=smtp.host.strip(),
            port=smtp.port,
            username=username or None,
            password=password or None,
            use_tls=bool(smtp.use_tls),
            use_ssl=bool(smtp.use_ssl),
        )

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

        send_mail(
            subject,
            body,
            smtp.server_email,
            [order.email],
            fail_silently=False,
            connection=connection,
        )
        msg = f"[order-email] sent OK → {order.email} (order #{order.order_number})"
        logger.info(msg)
        print(msg)
        return True
    except Exception as exc:
        msg = f"[order-email] FAILED order #{getattr(order, 'pk', '?')}: {exc}"
        logger.exception(msg)
        print(msg)
        return False
