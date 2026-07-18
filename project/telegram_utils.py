"""
Відправка сповіщень у Telegram (Bot API sendMessage).
Той самий підхід, що SMTP: fail-silently, async thread, API не блокується.

Фаза 2 (керування через бота: статус / email / viber) — див. telegram_bot.py.
"""
import html
import logging
import threading

import requests
from django.conf import settings as django_settings
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


def product_absolute_url(product) -> str:
    base = getattr(django_settings, "SITE_URL", "https://mrcarpet24.com").rstrip("/")
    try:
        path = product.get_absolute_url()
    except Exception:
        slug = getattr(product, "slug", "") or ""
        path = f"/catalog/product/{slug}/" if slug else ""
    if not path:
        return base
    return f"{base}{path}"


def send_telegram_message(text, fail_silently=True, parse_mode=None):
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
    if parse_mode:
        payload["parse_mode"] = parse_mode
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
        # HTML parse error → retry plain
        if parse_mode and not data.get("ok"):
            payload.pop("parse_mode", None)
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


def send_telegram_message_async(text, parse_mode=None):
    """Фонова відправка — HTTP-відповідь клієнту не чекає Telegram."""

    def _run():
        close_old_connections()
        try:
            ok = send_telegram_message(text, fail_silently=True, parse_mode=parse_mode)
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


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _order_items_lines(order, *, html_links=False):
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
        product = getattr(cp.product_attr, "product", None)
        title = getattr(product, "title", None) or "—"
        size = ""
        try:
            if cp.product_attr and cp.product_attr.size:
                size = f" ({cp.product_attr.size})"
        except Exception:
            pass
        length = f", {cp.length} м" if cp.length else ""
        label = f"{title}{size}{length} × {cp.quantity}"
        if html_links and product is not None:
            href = html.escape(product_absolute_url(product), quote=True)
            lines.append(f"• <a href=\"{href}\">{_esc(label)}</a>")
        else:
            lines.append(f"• {label}")
    return lines


def format_order_message(order, event="new"):
    """
    event: new | awaiting_payment | paid
    Returns HTML (Telegram parse_mode=HTML) with clickable product links.
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
        f"{_esc(header)} №{_esc(number)}",
        f"Статус: {_esc(order.get_status_display())}",
        f"Клієнт: {_esc(customer)}",
        f"Телефон: {_esc(order.phone or '—')}",
        f"Email: {_esc(order.email or '—')}",
        f"Місто: {_esc(order.city or '—')}",
        f"Адреса: {_esc(order.address or '—')}",
        f"Оплата: {_esc(order.get_payment_type_display())}",
        f"Сума: {_esc(_price(order.total_price))}",
    ]
    if order.message:
        lines.append(f"Коментар: {_esc(order.message)}")
    items = _order_items_lines(order, html_links=True)
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
    send_telegram_message_async(
        format_order_message(order, event=event),
        parse_mode="HTML",
    )


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
