"""
Daily readings of how the published videos are doing.

Deliberately built on what the tokens we already hold can answer, because the
alternative is dragging a human through a consent screen per network. What
each network gives us today, verified against the live API rather than the
docs:

* **YouTube** — views, likes, comments, via the API key. No OAuth at all.
* **Facebook** — views, likes, comments, from the video object's own fields.
  /video_insights would need read_insights; the plain fields do not.
* **Instagram** — likes and comments only. Views live behind
  instagram_manage_insights, which this token lacks.
* **Threads** — nothing. Every metric is behind threads_manage_insights.
* **TikTok** — nothing. Needs the video.list scope from a product we have not
  added, and adding a product while the content-posting audit is in review is
  not a trade worth making.

The gaps are recorded as unknown rather than zero, so a report never claims
Instagram got no views when it simply will not say.

For the two silent networks the honest answer is that GA4 covers them: every
product link carries a per-network utm_source, so "did it bring anyone" is
answerable even where "did anyone watch" is not.
"""

from __future__ import annotations

import logging
from datetime import date

from django.utils import timezone

from social.models import VideoDelivery, VideoMetric

logger = logging.getLogger(__name__)

#: How long a video keeps being re-read. Interest in a Short is mostly spent
#: within a week, and the row for day one — the comparable number — is written
#: long before that.
LOOKBACK_DAYS = 7


def fetch_for(delivery: VideoDelivery) -> dict[str, int | None] | None:
    """
    Counters for one delivery, or None when the network will not tell us.

    None and an exception are different outcomes: None means "asked and
    answered nothing to record", an exception means the call broke. Only the
    latter is worth a log line.
    """
    platform = delivery.platform
    if platform == VideoDelivery.Platform.YOUTUBE:
        from social.services import youtube

        return youtube.video_metrics(delivery.external_id)

    if platform == VideoDelivery.Platform.FACEBOOK:
        from social.services import meta

        return meta.facebook_video_metrics(delivery.external_id)

    if platform == VideoDelivery.Platform.INSTAGRAM:
        from social.services import meta

        return meta.instagram_media_metrics(delivery.external_id)

    # Threads and TikTok: see the module docstring. Not an error.
    return None


def due_deliveries(*, days: int = LOOKBACK_DAYS, now=None) -> list[VideoDelivery]:
    now = now or timezone.now()
    return list(
        VideoDelivery.objects.filter(
            status__in=VideoDelivery.SUCCESS_STATUSES,
            published_at__gte=now - timezone.timedelta(days=days),
        ).exclude(external_id="")
    )


def collect_once(*, days: int = LOOKBACK_DAYS, now=None) -> int:
    """
    Read every recent delivery once and store today's snapshot.

    Idempotent by (delivery, collected_on): running twice in a day updates the
    row rather than growing the table, which matters because the scheduler
    ticks every ten minutes and a restart must not double-count.

    One network failing must not cost the others their reading, so each is
    caught separately.
    """
    now = now or timezone.now()
    today: date = timezone.localtime(now).date()
    written = 0

    for delivery in due_deliveries(days=days, now=now):
        try:
            counters = fetch_for(delivery)
        except Exception as exc:
            logger.warning(
                "metrics: %s %s failed: %s", delivery.platform, delivery.external_id, exc
            )
            continue
        if counters is None:
            continue

        published = delivery.published_at or now
        age_hours = max(int((now - published).total_seconds() // 3600), 0)

        VideoMetric.objects.update_or_create(
            delivery=delivery,
            collected_on=today,
            defaults={
                "views": counters.get("views"),
                "likes": counters.get("likes"),
                "comments": counters.get("comments"),
                "age_hours": age_hours,
            },
        )
        written += 1

    return written


#: Networks that answer nothing today, and what it would cost to change that.
#: Named in the report rather than silently missing, so a run of empty lines
#: reads as a known limit instead of a broken collector.
SILENT_NETWORKS = {
    VideoDelivery.Platform.THREADS: "потрібен дозвіл threads_manage_insights",
    VideoDelivery.Platform.TIKTOK: "потрібен скоуп video.list (не чіпаємо під час аудиту)",
}

REPORT_DAYS = 7


def weekly_summary(*, days: int = REPORT_DAYS, now=None) -> dict[str, dict]:
    """
    Per-network totals over the window, from each video's latest reading.

    The latest reading per delivery, not the sum of all readings: the counters
    are cumulative, so adding up daily snapshots would count the same view
    once per day it survived.
    """
    now = now or timezone.now()
    since = timezone.localtime(now).date() - timezone.timedelta(days=days)

    latest: dict[int, VideoMetric] = {}
    for metric in VideoMetric.objects.filter(collected_on__gte=since).select_related(
        "delivery"
    ).order_by("collected_on"):
        latest[metric.delivery_id] = metric

    totals: dict[str, dict] = {}
    for metric in latest.values():
        bucket = totals.setdefault(
            metric.delivery.platform,
            {"videos": 0, "views": 0, "likes": 0, "comments": 0, "views_known": False},
        )
        bucket["videos"] += 1
        if metric.views is not None:
            bucket["views"] += metric.views
            bucket["views_known"] = True
        bucket["likes"] += metric.likes or 0
        bucket["comments"] += metric.comments or 0
    return totals


def format_summary(totals: dict[str, dict], *, days: int = REPORT_DAYS) -> str:
    labels = dict(VideoDelivery.Platform.choices)
    lines = [f"📊 Відео за {days} днів"]

    # Best first — the whole point of the report is which network to keep
    # feeding. Networks that do not report views sort last rather than as zero.
    def rank(item):
        return (1 if item[1]["views_known"] else 0, item[1]["views"])

    for platform, data in sorted(totals.items(), key=rank, reverse=True):
        views = f"{data['views']} 👁" if data["views_known"] else "перегляди н/д"
        lines.append(
            f"• {labels.get(platform, platform)}: {views} · "
            f"{data['likes']} ❤ · {data['comments']} 💬 "
            f"({data['videos']} відео)"
        )

    for platform, reason in SILENT_NETWORKS.items():
        if platform not in totals:
            lines.append(f"• {labels.get(platform, platform)}: без даних — {reason}")

    lines.append("")
    lines.append("Звідки прийшли покупці — GA4, кампанія daily-video.")
    return "\n".join(lines)


def report_weekly(*, days: int = REPORT_DAYS, now=None) -> str:
    """Send the digest to the video topic. Returns what was sent."""
    from social.services.comment_notify import notify_staff_text

    totals = weekly_summary(days=days, now=now)
    if not totals:
        return ""
    text = format_summary(totals, days=days)
    notify_staff_text(text, video=True)
    return text
