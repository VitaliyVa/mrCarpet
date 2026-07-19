"""IG/FB коменти → staff topic (дзеркало, як TG discussion).

Meta Webhooks пушить події на /api/meta/webhook/:
- object=page, field=feed → коменти під постами FB-сторінки
- object=instagram, field=comments → коменти під IG-медіа

Далі та сама труба, що й у Telegram: InboundComment → notify_staff_comment.
Захист від луп: власні коменти сторінки/IG-акаунта скіпаються.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections import OrderedDict
from datetime import datetime, timezone as dt_timezone

from django.conf import settings

from social.services.comment_notify import (
    PLATFORM_FACEBOOK,
    PLATFORM_INSTAGRAM,
    InboundComment,
    notify_staff_comment,
    staff_comments_configured,
)

logger = logging.getLogger(__name__)

# Meta ретраїть недоставлені події — легкий процесний дедуп
_SEEN_MAX = 500
_seen: OrderedDict[str, bool] = OrderedDict()


def _mark_seen(key: str) -> bool:
    """True якщо вже бачили; інакше запам'ятовує."""
    if not key:
        return False
    if key in _seen:
        return True
    _seen[key] = True
    while len(_seen) > _SEEN_MAX:
        _seen.popitem(last=False)
    return False


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """X-Hub-Signature-256: sha256=HMAC(app_secret, body).

    Без META_APP_SECRET приймаємо з warning — верифікація вмикається,
    щойно секрет з'явиться в .env.
    """
    secret = (getattr(settings, "META_APP_SECRET", "") or "").strip()
    if not secret:
        logger.warning("meta webhook: META_APP_SECRET empty, signature not verified")
        return True
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature_header[7:], expected)


def _page_id() -> str:
    return (getattr(settings, "META_PAGE_ID", "") or "").strip()


def _ig_user_id() -> str:
    return (getattr(settings, "META_IG_USER_ID", "") or "").strip()


def inbound_from_facebook_change(value: dict) -> InboundComment | None:
    """Поле feed: item=comment, verb=add. Skip власних комментів сторінки."""
    if not value or value.get("item") != "comment":
        return None
    if (value.get("verb") or "add") != "add":
        return None
    from_obj = value.get("from") or {}
    if str(from_obj.get("id") or "") == _page_id():
        return None  # наша ж відповідь — не дублювати
    text = (value.get("message") or "").strip()
    if not text:
        return None

    created_at = None
    if value.get("created_time"):
        try:
            created_at = datetime.fromtimestamp(
                int(value["created_time"]), tz=dt_timezone.utc
            )
        except Exception:
            created_at = None

    comment_id = str(value.get("comment_id") or "")
    post_id = str(value.get("post_id") or "")
    return InboundComment(
        platform=PLATFORM_FACEBOOK,
        text=text,
        author_name=(from_obj.get("name") or "").strip() or "Користувач",
        author_id=str(from_obj.get("id") or ""),
        post_url=f"https://www.facebook.com/{post_id}" if post_id else "",
        comment_url=(
            f"https://www.facebook.com/{comment_id}" if comment_id else ""
        ),
        created_at=created_at,
    )


def inbound_from_instagram_change(value: dict) -> InboundComment | None:
    """Поле comments IG-акаунта. Skip власних відповідей акаунта."""
    if not value:
        return None
    from_obj = value.get("from") or {}
    if str(from_obj.get("id") or "") == _ig_user_id():
        return None
    text = (value.get("text") or "").strip()
    if not text:
        return None

    media = value.get("media") or {}
    media_id = str(media.get("id") or "")
    post_url = _instagram_media_permalink(media_id) if media_id else ""

    return InboundComment(
        platform=PLATFORM_INSTAGRAM,
        text=text,
        author_name=(from_obj.get("username") or "").strip() or "Користувач",
        author_username=(from_obj.get("username") or "").strip(),
        author_id=str(from_obj.get("id") or ""),
        post_url=post_url,
    )


def _instagram_media_permalink(media_id: str) -> str:
    """Best-effort: постійний лінк на IG-пост через Graph."""
    try:
        from social.services.meta import _graph

        data = _graph("GET", media_id, params={"fields": "permalink"})
        return (data.get("permalink") or "").strip()
    except Exception:
        logger.info("IG permalink fetch failed media_id=%s", media_id)
        return ""


def handle_meta_webhook(payload: dict) -> int:
    """Розбирає пуш Meta, шле staff-алерти. Повертає кількість надісланих."""
    if not payload:
        return 0
    obj = (payload.get("object") or "").strip()
    sent = 0
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            field = (change.get("field") or "").strip()
            value = change.get("value") or {}

            comment = None
            dedupe_key = ""
            if obj == "page" and field == "feed":
                comment = inbound_from_facebook_change(value)
                dedupe_key = f"fb:{value.get('comment_id') or ''}"
            elif obj == "instagram" and field == "comments":
                comment = inbound_from_instagram_change(value)
                dedupe_key = f"ig:{value.get('id') or ''}"

            if not comment:
                continue
            if _mark_seen(dedupe_key):
                logger.info("meta comment duplicate skipped: %s", dedupe_key)
                continue
            if not staff_comments_configured():
                logger.warning("meta comment skip: staff chat not configured")
                continue
            result = notify_staff_comment(comment)
            if result.get("ok"):
                sent += 1
            else:
                logger.error(
                    "meta comment notify failed: %s", result.get("error")
                )
    return sent
