"""
Спільна відправка пошти через SMTPSettings з адмінки.
Той самий підхід, що й контактна форма: try/except, помилка не валить запит.
"""
import logging
import threading

from django.core.mail import get_connection, send_mail
from django.db import close_old_connections

from .models import SMTPSettings

logger = logging.getLogger(__name__)

# Щоб API не висів хвилинами на Gmail/файрволі
SMTP_TIMEOUT_SECONDS = 12


def get_smtp_connection():
    smtp = SMTPSettings.load()
    if not smtp.host or not smtp.server_email:
        raise ValueError("SMTPSettings incomplete: host/server_email required")

    password = (smtp.email_host_password or "").replace(" ", "").strip()
    username = (smtp.username or smtp.server_email or "").strip() or None

    connection = get_connection(
        host=smtp.host.strip(),
        port=smtp.port,
        username=username,
        password=password or None,
        use_tls=bool(smtp.use_tls),
        use_ssl=bool(smtp.use_ssl),
        timeout=SMTP_TIMEOUT_SECONDS,
    )
    return smtp, connection


def send_smtp_mail(
    subject, message, recipient_list, fail_silently=True, html_message=None
):
    """
    Синхронна відправка (як у ContactRequestCreateView).
    За замовчуванням fail_silently=True — помилка лише в лог.
    html_message — опційний HTML (multipart/alternative).
    """
    try:
        smtp, connection = get_smtp_connection()
        send_mail(
            subject,
            message,
            smtp.server_email,
            recipient_list,
            fail_silently=False,
            connection=connection,
            html_message=html_message,
        )
        return True
    except Exception as exc:
        logger.exception("SMTP send failed: %s", exc)
        print(f"[smtp] FAILED: {exc}")
        if not fail_silently:
            raise
        return False


def send_smtp_mail_async(subject, message, recipient_list, html_message=None):
    """Фонова відправка — HTTP-відповідь не чекає SMTP."""

    def _run():
        close_old_connections()
        try:
            ok = send_smtp_mail(
                subject,
                message,
                recipient_list,
                fail_silently=True,
                html_message=html_message,
            )
            if ok:
                print(f"[smtp] sent OK → {recipient_list}")
        finally:
            close_old_connections()

    threading.Thread(target=_run, daemon=True, name="smtp-mail").start()
