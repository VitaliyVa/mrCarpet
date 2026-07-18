"""
Відправка сповіщень у Telegram (Bot API sendMessage).
Той самий підхід, що SMTP: fail-silently, async thread, API не блокується.

Фаза 2 (керування через бота: статус / email / viber) — див. telegram_bot.py.
"""
import logging
import threading

import requests
from django.db import close_old_connections, transaction

from .models import TelegramSettings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_TIMEOUT_SECONDS = 12


def _get_settings():
    try:
        return TelegramSettings.load()
    except Exception as exc:
        logger.exception("TelegramSettings load failed: %s", exc)
        return None


def send_telegram_message(text, fail_silently=True):
    """
    Синхронна відправка тексту в налаштований chat_id.
    Повертає True при успіху, False якщо вимкнено / помилка.
    """
    settings = _get_settings()
    if not settings or not settings.is_configured:
        return False

    token = settings.bot_token.strip()
    chat_id = settings.chat_id.strip()
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    thread_id = (settings.message_thread_id or "").strip()
    if thread_id:
        try:
            payload["message_thread_id"] = int(thread_id)
        except ValueError:
            payload["message_thread_id"] = thread_id

    try:
        response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT_SECONDS)
        data = response.json() if response.content else {}
        if response.ok and data.get("ok"):
            return True
        logger.warning(
            "Telegram send failed: status=%s body=%s",
            response.status_code,
            data,
        )
        print(f"[telegram] FAILED: {response.status_code} {data}")
        if not fail_silently:
            response.raise_for_status()
        return False
    except Exception as exc:
        logger.exception("Telegram send failed: %s", exc)
        print(f"[telegram] FAILED: {exc}")
        if not fail_silently:
            raise
        return False


def send_telegram_message_async(text):
    """Фонова відправка — HTTP-відповідь клієнту не чекає Telegram."""

    def _run():
        close_old_connections()
        try:
            ok = send_telegram_message(text, fail_silently=True)
            if ok:
                print("[telegram] sent OK")
        finally:
            close_old_connections()

    threading.Thread(target=_run, daemon=True, name="telegram-notify").start()


def _should_notify(kind: str) -> bool:
    settings = _get_settings()
    if not settings or not settings.is_configured:
        return False
    flags = {
        "order": settings.notify_orders,
        "contact": settings.notify_contacts,
        "stock": settings.notify_stock,
    }
    return bool(flags.get(kind, True))


def _price(value):
    if value is None:
        return "—"
    try:
        return f"{float(value):.0f} грн"
    except (TypeError, ValueError):
        return str(value)


def _order_items_lines(order):
    try:
        cart = order.cart
    except Exception:
        return []
    lines = []
    try:
        products = cart.cart_products.select_related(
            "product_attr__product", "product_attr__size"
        ).all()
    except Exception:
        return []
    for cp in products:
        title = getattr(getattr(cp.product_attr, "product", None), "title", None) or "—"
        size = ""
        try:
            if cp.product_attr and cp.product_attr.size:
                size = f" ({cp.product_attr.size})"
        except Exception:
            pass
        length = f", {cp.length} м" if cp.length else ""
        lines.append(f"• {title}{size}{length} × {cp.quantity}")
    return lines


def format_order_message(order, event="new"):
    """
    event: new | awaiting_payment | paid
    """
    headers = {
        "new": "🛒 Нове замовлення",
        "awaiting_payment": "💳 Замовлення очікує оплати",
        "paid": "✅ Замовлення оплачено",
    }
    header = headers.get(event, "🛒 Замовлення")
    number = order.order_number or order.pk or "?"
    customer = f"{order.name} {order.surname}".strip() or "—"
    lines = [
        f"{header} №{number}",
        f"Статус: {order.get_status_display()}",
        f"Клієнт: {customer}",
        f"Телефон: {order.phone or '—'}",
        f"Email: {order.email or '—'}",
        f"Місто: {order.city or '—'}",
        f"Адреса: {order.address or '—'}",
        f"Оплата: {order.get_payment_type_display()}",
        f"Сума: {_price(order.total_price)}",
    ]
    if order.message:
        lines.append(f"Коментар: {order.message}")
    items = _order_items_lines(order)
    if items:
        lines.append("Товари:")
        lines.extend(items)
    return "\n".join(lines)


def format_contact_message(contact):
    return "\n".join(
        [
            "📩 Нова контактна форма",
            f"Ім'я: {contact.name}",
            f"Email: {contact.email}",
            f"Коментар: {contact.text}",
        ]
    )


def format_stock_message(inquiry):
    return "\n".join(
        [
            "📦 Запит наявності",
            f"Ім'я: {inquiry.name}",
            f"Телефон: {inquiry.phone}",
            f"Email: {inquiry.email}",
            f"Товар: {inquiry.product_title or '—'}",
            f"Розмір: {inquiry.size_label or '—'}",
        ]
    )


def notify_contact(contact):
    if not _should_notify("contact"):
        return
    send_telegram_message_async(format_contact_message(contact))


def notify_stock(inquiry):
    if not _should_notify("stock"):
        return
    send_telegram_message_async(format_stock_message(inquiry))


def notify_order(order, event="new"):
    if not _should_notify("order"):
        return
    send_telegram_message_async(format_order_message(order, event=event))


def enqueue_order_telegram(order_id, event="new"):
    """Після commit БД — TG у фон (як order email)."""

    def _after_commit():
        close_old_connections()
        try:
            from order.models import Order

            order = (
                Order.objects.filter(pk=order_id)
                .select_related("promocode")
                .first()
            )
            if not order:
                print(f"[telegram] skip: order #{order_id} not found")
                return
            notify_order(order, event=event)
            print(f"[telegram] queued order #{order.order_number} ({event})")
        except Exception as exc:
            logger.exception("enqueue order telegram failed: %s", exc)
            print(f"[telegram] enqueue FAILED: {exc}")
        finally:
            close_old_connections()

    transaction.on_commit(_after_commit)
