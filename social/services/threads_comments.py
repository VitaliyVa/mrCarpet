"""
Inbound Threads replies → staff Telegram topic.

Threads pushes replies over its own webhook rather than the Instagram/Page
one: topic `moderate`, field `replies`. The payload already carries the
username, text and permalink, so nothing has to be fetched back.

Polling exists as a fallback (`GET /{media-id}/conversation`) but neither it
nor `/replies` accepts a `since` parameter, so a poller would re-read whole
threads every cycle. The webhook makes that problem disappear.

One trap worth naming, because the endpoint reads like the obvious choice:
`GET /me/replies` returns replies *we wrote*, not replies we received. It is
useless for this and quietly returns plausible data.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections import OrderedDict
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.conf import settings

from social.services.comment_notify import (
    InboundComment,
    notify_staff_comment,
    staff_comments_configured,
)

logger = logging.getLogger(__name__)

PLATFORM_THREADS = "threads"

# Meta does not promise exactly-once delivery, so the same reply can arrive
# twice. The in-process cache catches the common case; the database check
# below survives a restart, which the cache does not.
_SEEN_MAX = 500
_seen: OrderedDict[str, bool] = OrderedDict()


def _mark_seen(key: str) -> bool:
    """True when this id was already handled."""
    if not key:
        return False
    if key in _seen:
        return True
    _seen[key] = True
    while len(_seen) > _SEEN_MAX:
        _seen.popitem(last=False)
    return False


def _already_alerted(reply_id: str) -> bool:
    """Survives a redeploy, unlike the in-memory cache."""
    if not reply_id:
        return False
    try:
        from social.models import SocialCommentReply

        return SocialCommentReply.objects.filter(
            platform=PLATFORM_THREADS, external_comment_id=reply_id
        ).exists()
    except Exception:
        logger.exception("threads dedupe lookup failed")
        return False


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify X-Hub-Signature-256 against the *Threads* app secret.

    Signed with the Threads secret, not the Meta one — the two apps share a
    dashboard but not their keys.
    """
    secret = (getattr(settings, "THREADS_APP_SECRET", "") or "").strip()
    if not secret:
        # Same posture as the Meta webhook: warn rather than lock ourselves out
        # of a feature because a secret has not been set yet.
        logger.warning("THREADS_APP_SECRET unset — webhook signature not checked")
        return True
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header[len("sha256=") :])


def _own_user_id() -> str:
    try:
        from social.models import ThreadsToken

        return (ThreadsToken.load().user_id or "").strip()
    except Exception:
        return ""


def _own_username() -> str:
    try:
        from social.models import ThreadsToken

        return (ThreadsToken.load().username or "").strip().lstrip("@")
    except Exception:
        return ""


def inbound_from_threads_reply(value: dict) -> InboundComment | None:
    """
    Parse one `replies` webhook value into an InboundComment.

    Returns None for our own replies: answering a customer must not bounce
    straight back into the staff topic as if it were a new question.
    """
    if not value:
        return None

    text = (value.get("text") or "").strip()
    if not text:
        return None

    username = (value.get("username") or "").strip().lstrip("@")
    author_id = str(value.get("owner_id") or value.get("user_id") or "")

    # The webhook payload has no is_reply_owned_by_me, so compare identities.
    own_user, own_name = _own_user_id(), _own_username()
    if (own_user and author_id and author_id == own_user) or (
        own_name and username and username.lower() == own_name.lower()
    ):
        return None

    created_at = None
    stamp = value.get("timestamp")
    if stamp:
        try:
            created_at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            try:
                created_at = datetime.fromtimestamp(int(stamp), tz=dt_timezone.utc)
            except (TypeError, ValueError):
                created_at = None

    root = value.get("root_post") or {}
    root_id = str(root.get("id") or "")
    permalink = (value.get("permalink") or "").strip()

    return InboundComment(
        platform=PLATFORM_THREADS,
        text=text,
        author_name=username or "Користувач",
        author_username=username,
        author_id=author_id,
        post_url=f"https://www.threads.net/@{own_name}/post/{root.get('shortcode')}"
        if root.get("shortcode") and own_name
        else "",
        comment_url=permalink,
        created_at=created_at,
        external_id=str(value.get("id") or ""),
        parent_post_id=root_id,
    )


def handle_threads_webhook(payload: dict) -> int:
    """
    Route a Threads webhook payload to the staff topic.

    Returns the number of alerts sent. Never raises: a webhook that answers
    with an error gets retried and eventually unsubscribed by Meta.
    """
    if not payload:
        return 0

    field = ""
    values = payload.get("values")
    value: dict[str, Any] = {}
    if isinstance(values, dict):
        field = (values.get("field") or "").strip()
        value = values.get("value") or {}
    elif isinstance(values, list) and values:
        first = values[0] or {}
        field = (first.get("field") or "").strip()
        value = first.get("value") or {}

    if field != "replies":
        logger.info("threads webhook: ignoring field=%s", field or "?")
        return 0

    comment = inbound_from_threads_reply(value)
    if not comment:
        return 0

    reply_id = comment.external_id
    if _mark_seen(f"th:{reply_id}") or _already_alerted(reply_id):
        logger.info("threads reply duplicate skipped: %s", reply_id)
        return 0

    if not staff_comments_configured():
        logger.warning("threads reply skip: staff chat not configured")
        return 0

    # Everything we publish to Threads is a daily video, so replies always
    # belong in the video topic. No per-post lookup needed here, unlike
    # Instagram — which carries both Reels and product carousels.
    result = notify_staff_comment(comment, video=True)
    if not result.get("ok"):
        logger.error("threads reply notify failed: %s", result.get("error"))
        return 0
    return 1
