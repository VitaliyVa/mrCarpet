"""
Inbound YouTube comments → staff Telegram topic.

YouTube has no webhooks for comments, so this polls. Two things shape the
design.

**An API key, not the upload token.** `commentThreads.list` needs
`youtube.readonly` or `youtube.force-ssl`, and our OAuth grant deliberately
carries only `youtube.upload`. Comments on a public video are public data,
so a plain API key reads them — no second consent screen, and the token the
uploader depends on is left alone.

**Polling by video, not by channel.** `allThreadsRelatedToChannelId` needs
OAuth; `videoId` works with a key. We know exactly which videos are ours
from VideoDelivery, so per-video polling is both possible and cheaper: a
handful of calls against a 10,000-unit daily budget.

Order is `time` (newest first) so the walk can stop at the first comment
already seen instead of paging through the whole history.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone

import requests
from django.conf import settings
from django.utils import timezone

from social.models import VideoDelivery
from social.services.comment_notify import (
    InboundComment,
    notify_staff_comment,
    staff_comments_configured,
)

logger = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
HTTP_TIMEOUT = 30
PLATFORM_YOUTUBE = "youtube"

#: How far back to keep checking a video for new comments. Interest in a
#: Short dies quickly, and polling every video we ever posted would grow
#: without bound.
LOOKBACK_DAYS = 7
#: Per video, per run. `order=time` puts new ones first, so this is a ceiling
#: on a quiet day rather than a limit on what we can see.
MAX_PER_VIDEO = 20


def api_key() -> str:
    return (getattr(settings, "YOUTUBE_API_KEY", "") or "").strip()


def comments_configured() -> bool:
    return bool(api_key())


def _own_channel_id() -> str:
    from social.models import YouTubeToken

    return (YouTubeToken.load().channel_id or "").strip()


def _already_alerted(comment_id: str) -> bool:
    if not comment_id:
        return True
    try:
        from social.models import SocialCommentReply

        return SocialCommentReply.objects.filter(
            platform=PLATFORM_YOUTUBE, external_comment_id=comment_id
        ).exists()
    except Exception:
        logger.exception("youtube dedupe lookup failed")
        return True  # Better a missed alert than a repeated one every hour.


def _parse_time(value: str):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _inbound(snippet: dict, video_id: str, comment_id: str) -> InboundComment | None:
    text = (snippet.get("textOriginal") or snippet.get("textDisplay") or "").strip()
    if not text:
        return None

    author_channel = ((snippet.get("authorChannelId") or {}).get("value") or "").strip()
    # Our own replies must not come back as fresh questions.
    if author_channel and author_channel == _own_channel_id():
        return None

    return InboundComment(
        platform=PLATFORM_YOUTUBE,
        text=text,
        author_name=(snippet.get("authorDisplayName") or "").strip() or "Користувач",
        author_id=author_channel,
        post_url=f"https://www.youtube.com/shorts/{video_id}",
        comment_url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
        created_at=_parse_time(snippet.get("publishedAt")),
        external_id=comment_id,
        parent_post_id=video_id,
    )


def fetch_comments(video_id: str) -> list[InboundComment]:
    """Newest comments on one video, ours filtered out."""
    if not comments_configured():
        return []

    try:
        resp = requests.get(
            f"{API}/commentThreads",
            params={
                "part": "snippet",
                "videoId": video_id,
                "order": "time",
                "maxResults": MAX_PER_VIDEO,
                "textFormat": "plainText",
                "key": api_key(),
            },
            timeout=HTTP_TIMEOUT,
        )
        data = resp.json() if resp.content else {}
    except requests.RequestException as exc:
        logger.warning("youtube comments HTTP error for %s: %s", video_id, exc)
        return []
    except ValueError:
        logger.warning("youtube comments returned non-JSON for %s", video_id)
        return []

    if resp.status_code >= 400:
        reason = ((data.get("error") or {}).get("errors") or [{}])[0].get("reason", "")
        if reason == "commentsDisabled":
            logger.info("youtube comments disabled on %s", video_id)
        else:
            logger.warning(
                "youtube comments %s for %s: %s",
                resp.status_code,
                video_id,
                str(data)[:300],
            )
        return []

    out = []
    for item in data.get("items") or []:
        top = ((item.get("snippet") or {}).get("topLevelComment") or {})
        comment_id = str(top.get("id") or "")
        comment = _inbound(top.get("snippet") or {}, video_id, comment_id)
        if comment:
            out.append(comment)
    return out


def recent_video_ids(*, days: int = LOOKBACK_DAYS, now=None) -> list[str]:
    """YouTube videos we published recently, newest first."""
    now = now or timezone.now()
    cutoff = now - timezone.timedelta(days=days)
    return list(
        VideoDelivery.objects.filter(
            platform=VideoDelivery.Platform.YOUTUBE,
            status__in=VideoDelivery.SUCCESS_STATUSES,
            published_at__gte=cutoff,
        )
        .exclude(external_id="")
        .order_by("-published_at")
        .values_list("external_id", flat=True)
    )


def poll_once(*, days: int = LOOKBACK_DAYS, now=None) -> int:
    """
    Check recent videos and mirror anything new. Returns alerts sent.

    Never raises: this runs from a scheduler loop, and a bad hour must not
    take the loop down with it.
    """
    if not comments_configured():
        logger.info("youtube comments skip: YOUTUBE_API_KEY not set")
        return 0
    if not staff_comments_configured():
        logger.warning("youtube comments skip: staff chat not configured")
        return 0

    sent = 0
    for video_id in recent_video_ids(days=days, now=now):
        for comment in fetch_comments(video_id):
            if _already_alerted(comment.external_id):
                # order=time means the rest of this video is older still.
                break
            try:
                # Everything we put on YouTube is a daily video.
                result = notify_staff_comment(comment, video=True)
            except Exception:
                logger.exception("youtube comment notify crashed")
                continue
            if result.get("ok"):
                sent += 1
            else:
                logger.error("youtube comment notify failed: %s", result.get("error"))
    if sent:
        logger.info("youtube comments: %s alert(s) sent", sent)
    return sent
