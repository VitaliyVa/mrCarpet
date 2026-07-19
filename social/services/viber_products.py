"""Product → Viber channel post (Viber Channels Post API).

Дзеркало telegram_products для Viber-каналу. Обмеження Viber:
одне фото на повідомлення (без медіа-групи), caption у picture ≤ 768
символів. Постинг подвійно загейчений: settings.VIBER_AUTH_TOKEN +
SocialSettings.viber_posting_enabled (майстер-рубильник, default False).
"""

from __future__ import annotations

import logging
import threading

import requests
from django.conf import settings
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)

VIBER_API = "https://chatapi.viber.com/pa"
TIMEOUT = 20
_PICTURE_TEXT_MAX = 768
_TEXT_MAX = 7000


def _token() -> str:
    return (getattr(settings, "VIBER_AUTH_TOKEN", "") or "").strip()


def viber_configured() -> bool:
    return bool(_token())


def viber_posting_enabled() -> bool:
    """Майстер-рубильник: токен є І увімкнено в Social settings."""
    if not viber_configured():
        return False
    from social.models import SocialSettings

    return bool(SocialSettings.load().viber_posting_enabled)


# get_account_info — 1 виклик на процес, superadmin id стабільний
_superadmin_cache: dict[str, str] = {}


def _superadmin_id(token: str) -> str:
    cached = _superadmin_cache.get(token)
    if cached:
        return cached
    resp = requests.post(
        f"{VIBER_API}/get_account_info",
        json={},
        headers={"X-Viber-Auth-Token": token},
        timeout=TIMEOUT,
    )
    data = resp.json() if resp.content else {}
    if data.get("status") != 0:
        raise RuntimeError(f"Viber get_account_info failed: {str(data)[:300]}")
    for member in data.get("members", []):
        if member.get("role") == "superadmin":
            sid = member.get("id") or ""
            if sid:
                _superadmin_cache[token] = sid
                return sid
    raise RuntimeError("Viber: superadmin not found in channel members")


def _caption(product) -> str:
    """Той самий зміст, що TG/IG: назва + розміри/ціни + лінк."""
    from project.telegram_utils import product_absolute_url
    from social.services.product_post import product_caption_text

    text = product_caption_text(product)
    url = product_absolute_url(product)
    if url and url not in text:
        text = f"{text}\n\n{url}"
    return text


def post_product_to_viber(product) -> dict:
    """Прямий пост у канал. Гейт viber_posting_enabled — на боці викликача
    (signal/admin) або через force-виклик тут не обходиться свідомо:
    без токена все одно нічого не полетить."""
    token = _token()
    if not token:
        return {"ok": False, "error": "VIBER_AUTH_TOKEN not set"}
    try:
        from social.services.telegram_products import _product_photo_urls

        text = _caption(product)
        photos = _product_photo_urls(product)
        sender = _superadmin_id(token)
        if photos:
            payload = {
                "from": sender,
                "type": "picture",
                "text": text[:_PICTURE_TEXT_MAX],
                "media": photos[0],
            }
        else:
            payload = {
                "from": sender,
                "type": "text",
                "text": text[:_TEXT_MAX],
            }
        resp = requests.post(
            f"{VIBER_API}/post",
            json=payload,
            headers={"X-Viber-Auth-Token": token},
            timeout=TIMEOUT,
        )
        data = resp.json() if resp.content else {}
        if data.get("status") != 0:
            return {"ok": False, "error": str(data)[:500]}
        return {"ok": True, "result": data}
    except Exception as exc:
        logger.exception("Viber product post failed")
        return {"ok": False, "error": str(exc)}


def enqueue_product_viber_post(product_id: int) -> None:
    """Авто-режим: пост після коміту транзакції (як TG/Meta)."""

    def _run():
        close_old_connections()
        try:
            from catalog.models import Product

            if not viber_posting_enabled():
                logger.info(
                    "Viber post skipped (disabled) pk=%s", product_id
                )
                return
            product = Product.objects.filter(pk=product_id).first()
            if not product:
                logger.warning(
                    "Viber product post skipped: Product pk=%s not found",
                    product_id,
                )
                return
            result = post_product_to_viber(product)
            if not result.get("ok"):
                logger.error(
                    "Viber product post failed pk=%s: %s",
                    product_id,
                    result.get("error"),
                )
        except Exception:
            logger.exception("enqueue viber post failed")
        finally:
            close_old_connections()

    def _schedule():
        threading.Thread(target=_run, daemon=True).start()

    transaction.on_commit(_schedule)
