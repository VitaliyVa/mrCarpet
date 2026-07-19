"""
Staff notifications for inbound social comments (Telegram now; IG/FB later).

Outbound only → SocialSettings.staff_comments_chat_id (e.g. «mr.Carpet comments»).
Never routes into orders AI / family chat_id.
"""

from __future__ import annotations

import html
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Any

import requests
from django.db import close_old_connections
from django.utils import timezone

from project.models import TelegramSettings
from social.models import SocialSettings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TIMEOUT = 20

PLATFORM_TELEGRAM = "telegram"
PLATFORM_INSTAGRAM = "instagram"
PLATFORM_FACEBOOK = "facebook"

PLATFORM_LABELS = {
    PLATFORM_TELEGRAM: "Telegram",
    PLATFORM_INSTAGRAM: "Instagram",
    PLATFORM_FACEBOOK: "Facebook",
}


@dataclass
class InboundComment:
    """Normalized comment from any social platform → staff alert."""

    platform: str
    text: str
    author_name: str = ""
    author_username: str = ""
    author_id: str = ""
    post_title: str = ""
    post_url: str = ""
    comment_url: str = ""
    created_at: datetime | None = None
    raw_chat_id: str = ""


def _staff_target() -> tuple[str, str]:
    """(chat_id, thread_id) — thread optional; chat falls back to family orders chat."""
    social = SocialSettings.load()
    chat = (social.staff_comments_chat_id or "").strip()
    thread = (getattr(social, "staff_comments_thread_id", "") or "").strip()
    if not chat:
        try:
            chat = (TelegramSettings.load().chat_id or "").strip()
        except Exception:
            chat = ""
    return chat, thread


def staff_comments_configured() -> bool:
    social = SocialSettings.load()
    token = _bot_token()
    chat, thread = _staff_target()
    if not (social.staff_comments_enabled and token and chat):
        return False
    # Forum mode in family chat requires a dedicated topic
    try:
        family = (TelegramSettings.load().chat_id or "").strip()
    except Exception:
        family = ""
    if family and chat == family and not thread:
        return False
    return True


def notify_staff_comment(comment: InboundComment) -> dict[str, Any]:
    """Send formatted alert to staff comments chat/topic. Safe from any adapter."""
    if not staff_comments_configured():
        return {"ok": False, "error": "staff comments chat/topic not configured"}
    text = (comment.text or "").strip()
    if not text:
        return {"ok": False, "error": "empty comment"}

    chat_id, thread_id = _staff_target()
    token = _bot_token()
    body = format_staff_comment_html(comment)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": body[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if thread_id:
        try:
            payload["message_thread_id"] = int(thread_id)
        except ValueError:
            payload["message_thread_id"] = thread_id

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json=payload,
            timeout=TIMEOUT,
        )
        data = resp.json() if resp.content else {}
        if not data.get("ok"):
            logger.error("staff comment notify failed: %s", data)
            return {"ok": False, "error": str(data)[:500]}
        return {"ok": True, "result": data.get("result")}
    except Exception as exc:
        logger.exception("staff comment notify failed")
        return {"ok": False, "error": str(exc)}


def enqueue_staff_comment_notify(comment: InboundComment) -> None:
    def _run():
        close_old_connections()
        try:
            notify_staff_comment(comment)
        except Exception:
            logger.exception("enqueue staff comment notify failed")
        finally:
            close_old_connections()

    threading.Thread(target=_run, daemon=True).start()


def format_staff_comment_html(comment: InboundComment) -> str:
    platform = PLATFORM_LABELS.get(comment.platform, comment.platform or "?")
    when = comment.created_at or timezone.now()
    if timezone.is_aware(when):
        when_local = timezone.localtime(when)
    else:
        when_local = when
    when_s = when_local.strftime("%d.%m.%Y %H:%M")

    author = html.escape((comment.author_name or "Анонім").strip() or "Анонім")
    if comment.author_username:
        author += f" (@{html.escape(comment.author_username.lstrip('@'))})"

    lines = [
        f"💬 <b>Коментар · {html.escape(platform)}</b>",
        "",
    ]
    if comment.post_title:
        lines.append(f"📌 Пост: {html.escape(comment.post_title[:200])}")
    if comment.post_url:
        lines.append(
            f'🔗 Пост: <a href="{html.escape(comment.post_url)}">{html.escape(comment.post_url)}</a>'
        )
    lines.append(f"👤 Автор: {author}")
    lines.append(f"🕒 {html.escape(when_s)}")
    if comment.comment_url:
        lines.append(
            f'🧵 Тред: <a href="{html.escape(comment.comment_url)}">{html.escape(comment.comment_url)}</a>'
        )
    lines.append("")
    lines.append("Текст:")
    lines.append(html.escape(comment.text.strip()[:1500]))
    return "\n".join(lines)


def inbound_from_telegram_discussion(msg: dict) -> InboundComment | None:
    """
    Parse products discussion message into InboundComment.
    Returns None for channel auto-forwards, bots, empty text.
    """
    if not msg:
        return None
    if msg.get("is_automatic_forward"):
        return None
    sender_chat = msg.get("sender_chat") or {}
    if (sender_chat.get("type") or "") == "channel":
        return None
    from_user = msg.get("from") or {}
    if from_user.get("is_bot"):
        return None

    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not text or text.startswith("/"):
        return None

    post_title, post_url = _telegram_parent_post(msg.get("reply_to_message") or {})
    author_name = " ".join(
        p
        for p in (from_user.get("first_name") or "", from_user.get("last_name") or "")
        if p
    ).strip()
    username = (from_user.get("username") or "").strip()

    created_at = None
    if msg.get("date"):
        try:
            created_at = datetime.fromtimestamp(
                int(msg["date"]), tz=dt_timezone.utc
            )
        except Exception:
            created_at = timezone.now()

    chat = msg.get("chat") or {}
    comment_url = ""
    # Private supergroup deep link is awkward without username; skip if unknown

    return InboundComment(
        platform=PLATFORM_TELEGRAM,
        text=text,
        author_name=author_name,
        author_username=username,
        author_id=str(from_user.get("id") or ""),
        post_title=post_title,
        post_url=post_url,
        comment_url=comment_url,
        created_at=created_at,
        raw_chat_id=str(chat.get("id") or ""),
    )


def notify_telegram_discussion_message(msg: dict) -> bool:
    """Build + enqueue staff notify. True if a notify was queued."""
    comment = inbound_from_telegram_discussion(msg)
    if not comment:
        return False
    if not staff_comments_configured():
        return False
    enqueue_staff_comment_notify(comment)
    return True


def _telegram_parent_post(reply: dict) -> tuple[str, str]:
    if not reply:
        return "", ""
    title = (reply.get("caption") or reply.get("text") or "").strip()
    # First line only for title preview
    if title:
        title = title.splitlines()[0][:180]

    post_url = ""
    fwd_chat = reply.get("forward_from_chat") or reply.get("sender_chat") or {}
    username = (fwd_chat.get("username") or "").strip()
    fwd_mid = reply.get("forward_from_message_id") or reply.get("message_id")
    if username and fwd_mid:
        post_url = f"https://t.me/{username}/{fwd_mid}"
    return title, post_url


def _bot_token() -> str:
    try:
        return (TelegramSettings.load().bot_token or "").strip()
    except Exception:
        return ""
