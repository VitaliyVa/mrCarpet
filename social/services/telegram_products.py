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


def post_product_to_channel(product, *, force: bool = False) -> dict[str, Any]:
    social = SocialSettings.load()
    channel = (social.products_channel_id or "").strip()
    token = _bot_token()
    if not token or not channel:
        return {"ok": False, "error": "products channel / bot not configured"}

    title = html.escape(product.title or "Товар")
    url = product_absolute_url(product)
    price_line = _price_line(product)
    text = (
        f"<b>{title}</b>\n"
        f"{html.escape(price_line)}\n"
        f'<a href="{html.escape(url)}"></a>'
        f'🔗 <a href="{html.escape(url)}">Дивитись на сайті</a>'
    )

    photo_url = ""
    try:
        if product.image:
            from social.services.media_urls import absolute_media_url

            photo_url = absolute_media_url(product.image)
    except Exception:
        photo_url = ""

    try:
        if photo_url.startswith("http"):
            resp = requests.post(
                f"{TELEGRAM_API}/bot{token}/sendPhoto",
                json={
                    "chat_id": channel,
                    "photo": photo_url,
                    "caption": text[:1024],
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
                    "text": text,
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


def enqueue_product_channel_post(product_id: int) -> None:
    def _run():
        close_old_connections()
        try:
            from catalog.models import Product

            product = Product.objects.filter(pk=product_id).first()
            if product:
                post_product_to_channel(product)
        except Exception:
            logger.exception("enqueue product channel failed")
        finally:
            close_old_connections()

    threading.Thread(target=_run, daemon=True).start()


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
