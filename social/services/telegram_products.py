"""Telegram products channel: new product posts + comment replies."""

from __future__ import annotations

import html
import logging
import re
import threading
from typing import Any

import requests
from django.conf import settings as django_settings
from django.db import close_old_connections

from project.models import TelegramSettings
from project.telegram_utils import product_absolute_url
from social.models import SocialSettings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TIMEOUT = 20

# Whitelist intents for auto-reply in discussion group
_PRICE_RE = re.compile(r"\b(цін|цена|price|скільки|сколько|грн)\w*", re.I)
_SIZE_RE = re.compile(r"\b(розмір|размер|size|габарит)\w*", re.I)
_STOCK_RE = re.compile(r"\b(наявн|в\s*наявності|есть|stock|коли\s*буде)\w*", re.I)
_DELIVERY_RE = re.compile(r"\b(доставк|доставка|нова\s*пошта|np|shipping)\w*", re.I)


def _bot_token() -> str:
    try:
        return (TelegramSettings.load().bot_token or "").strip()
    except Exception:
        return ""


def products_channel_configured() -> bool:
    social = SocialSettings.load()
    return bool(_bot_token() and (social.products_channel_id or "").strip())


# Telegram media group / caption limits
_TG_MAX_PHOTOS = 10
_TG_CAPTION_MAX = 1024


def post_product_to_channel(product, *, force: bool = False) -> dict[str, Any]:
    social = SocialSettings.load()
    channel = (social.products_channel_id or "").strip()
    token = _bot_token()
    if not token or not channel:
        return {"ok": False, "error": "products channel / bot not configured"}

    text = _product_caption_html(product)
    photo_urls = _product_photo_urls(product)

    try:
        if len(photo_urls) >= 2:
            media = []
            for i, url in enumerate(photo_urls[:_TG_MAX_PHOTOS]):
                item: dict[str, Any] = {"type": "photo", "media": url}
                if i == 0:
                    item["caption"] = text[:_TG_CAPTION_MAX]
                    item["parse_mode"] = "HTML"
                media.append(item)
            resp = requests.post(
                f"{TELEGRAM_API}/bot{token}/sendMediaGroup",
                json={
                    "chat_id": channel,
                    "media": media,
                    "disable_notification": False,
                },
                timeout=TIMEOUT,
            )
        elif len(photo_urls) == 1:
            resp = requests.post(
                f"{TELEGRAM_API}/bot{token}/sendPhoto",
                json={
                    "chat_id": channel,
                    "photo": photo_urls[0],
                    "caption": text[:_TG_CAPTION_MAX],
                    "parse_mode": "HTML",
                    "disable_notification": False,
                },
                timeout=TIMEOUT,
            )
        else:
            resp = requests.post(
                f"{TELEGRAM_API}/bot{token}/sendMessage",
                json={
                    "chat_id": channel,
                    "text": text[:4096],
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=TIMEOUT,
            )
        data = resp.json() if resp.content else {}
        if not data.get("ok"):
            return {"ok": False, "error": str(data)[:500]}
        return {"ok": True, "result": data.get("result")}
    except Exception as exc:
        logger.exception("TG product post failed")
        return {"ok": False, "error": str(exc)}


def _product_photo_urls(product) -> list[str]:
    """Main image + gallery (ProductImage), HTTPS only, max 10, de-duped."""
    from social.services.media_urls import absolute_media_url

    urls: list[str] = []
    seen: set[str] = set()

    def _add(field) -> None:
        if not field:
            return
        try:
            url = absolute_media_url(field)
        except Exception:
            return
        if not url.startswith("http"):
            return
        if url in seen:
            return
        seen.add(url)
        urls.append(url)

    _add(getattr(product, "image", None))
    try:
        extras = product.images.order_by("sort_order", "id")
    except Exception:
        extras = []
    for img in extras:
        _add(getattr(img, "image", None))
        if len(urls) >= _TG_MAX_PHOTOS:
            break
    return urls[:_TG_MAX_PHOTOS]


def _product_caption_html(product) -> str:
    title = html.escape(product.title or "Товар")
    url = product_absolute_url(product)
    footer = (
        f'<a href="{html.escape(url)}"></a>'
        f'🔗 <a href="{html.escape(url)}">Дивитись на сайті</a>'
    )
    sizes_block = _sizes_block(product)
    if sizes_block:
        body = sizes_block
    else:
        price_line = _price_line(product)
        body = html.escape(price_line) if price_line else ""

    # Fit title + body + footer into Telegram caption limit
    head = f"<b>{title}</b>"
    budget = _TG_CAPTION_MAX - len(head) - len(footer) - 2
    if body and len(body) > budget:
        if budget < 40:
            body = ""
        else:
            cut = body[: max(0, budget - 1)]
            body = cut.rsplit("\n", 1)[0] + "…"
    parts = [head]
    if body:
        parts.append(body)
    parts.append(footer)
    return "\n".join(parts)


def _sizes_block(product) -> str:
    """List fixed sizes + optional custom (м²) for channel caption."""
    lines: list[str] = []
    try:
        attrs = list(
            product.get_size_attrs()
            .select_related("size")
            .order_by("sort_order", "id")
        )
    except Exception:
        attrs = []

    for attr in attrs:
        size_title = ""
        try:
            size_title = (attr.size.title if attr.size_id else "") or ""
        except Exception:
            size_title = ""
        size_title = size_title.strip() or "розмір"
        try:
            price = attr.get_total_price()
        except Exception:
            price = attr.price
        if price is None:
            price_s = "—"
        else:
            price_s = f"{price} грн"
        stock = "" if getattr(attr, "in_stock", True) else " · немає"
        lines.append(f"• {html.escape(size_title)} — {html.escape(str(price_s))}{stock}")

    if not lines:
        return ""
    return "Розміри:\n" + "\n".join(lines)


def enqueue_product_channel_post(product_id: int) -> None:
    """Post after DB commit — avoid race where worker thread queries before save lands."""
    from django.db import transaction

    def _run():
        close_old_connections()
        try:
            from catalog.models import Product

            product = Product.objects.filter(pk=product_id).first()
            if not product:
                logger.warning(
                    "TG product post skipped: Product pk=%s not found", product_id
                )
                return
            result = post_product_to_channel(product)
            if not result.get("ok"):
                logger.error(
                    "TG product post failed pk=%s: %s",
                    product_id,
                    result.get("error"),
                )
        except Exception:
            logger.exception("enqueue product channel failed")
        finally:
            close_old_connections()

    def _schedule():
        threading.Thread(target=_run, daemon=True).start()

    transaction.on_commit(_schedule)


def handle_discussion_comment(update: dict) -> bool:
    """
    If update is a comment in products discussion group matching whitelist,
    reply with product FAQ. Returns True if handled (caller should skip AI agent).
    """
    social = SocialSettings.load()
    if not social.products_bot_replies:
        return False
    discussion = (social.products_discussion_chat_id or "").strip()
    if not discussion:
        return False

    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if chat_id != discussion:
        return False

    # Ignore channel forwards without text questions
    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not text or text.startswith("/"):
        return False

    reply = _build_reply(text)
    if not reply:
        return False

    token = _bot_token()
    if not token:
        return False

    try:
        requests.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json={
                "chat_id": discussion,
                "text": reply,
                "reply_to_message_id": msg.get("message_id"),
                "disable_web_page_preview": True,
            },
            timeout=TIMEOUT,
        )
    except Exception:
        logger.exception("discussion reply failed")
    return True


def _build_reply(text: str) -> str:
    if _PRICE_RE.search(text):
        return (
            "Ціни вказані на картці товару на сайті і залежать від розміру. "
            f"Каталог: {getattr(django_settings, 'SITE_URL', 'https://mrcarpet24.com')}/catalog/"
        )
    if _SIZE_RE.search(text):
        return (
            "Розміри обираються на сторінці товару (ярлики см). "
            "Якщо потрібен нестандарт — напишіть довжину/ширину, менеджер підкаже."
        )
    if _STOCK_RE.search(text):
        return (
            "Наявність по розмірах видно на сайті. "
            "Немає в наявності — можна залишити запит «Дізнатись про наявність» на картці."
        )
    if _DELIVERY_RE.search(text):
        return (
            "Доставка Новою Поштою по Україні. "
            "Умови та безкоштовна доставка — у розділі Доставка на сайті."
        )
    return ""


def _price_line(product) -> str:
    try:
        attr = product.get_default_size_attr()
        if attr is None:
            return ""
        if getattr(attr, "custom_attribute", False):
            return f"від {attr.custom_price} грн/м²"
        return f"{attr.get_total_price()} грн"
    except Exception:
        return ""
