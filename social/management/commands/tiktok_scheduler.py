"""
Daemon: generate the TikTok post at 04:00 Kyiv, publish it at 18:00.

Same shape as ga4_weekly_scheduler — a small compose service rather than a
host crontab, so the schedule lives with the code and survives a redeploy.

The two times are split because the work and the audience want different
hours: two model calls and an ffmpeg render belong on an idle droplet at
night, while the post itself should land when people are actually scrolling.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

KYIV = ZoneInfo("Europe/Kyiv")

GENERATE_HOUR = 4
PUBLISH_HOUR = 18
# A failed run must not spin: back off before the loop looks at the clock again.
COOLDOWN_SEC = 90
# Stagger granularity: networks go out 20 minutes apart, so the loop has to
# wake at least that often to release them.
TICK_MINUTES = 10


def next_daily_slot(now: datetime | None = None) -> tuple[datetime, str]:
    """
    The next of the two daily slots, crossing the day boundary when needed.

    Kept separate from next_run so the day-boundary logic stays testable on
    its own — the hourly poll would otherwise win almost every comparison and
    hide it.
    """
    now = (now or datetime.now(KYIV)).astimezone(KYIV)
    candidates = []
    for day_offset in (0, 1):
        day = now + timedelta(days=day_offset)
        for hour, action in ((GENERATE_HOUR, "generate"), (PUBLISH_HOUR, "publish")):
            moment = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            if moment > now:
                candidates.append((moment, action))
    return min(candidates, key=lambda pair: pair[0])


def next_run(now: datetime | None = None) -> tuple[datetime, str]:
    """
    Return the next scheduled moment and which step it is.

    Three kinds of work share one loop: the two daily slots and an hourly
    comment poll. YouTube has no webhooks for comments, so the only way to
    see them is to ask — the other networks push and need nothing here.

    A tie goes to the daily slot: at 04:00 generating the video matters more
    than checking for comments, and the poll comes round again in an hour.
    """
    now = (now or datetime.now(KYIV)).astimezone(KYIV)
    daily_moment, daily_action = next_daily_slot(now)

    # Every ten minutes. Two jobs share the tick: releasing networks whose
    # stagger slot has come round, and — on the hour — asking YouTube for new
    # comments. Ten is the granularity the 20-minute stagger needs; finer would
    # just burn wakeups on nothing.
    tick = (now + timedelta(minutes=TICK_MINUTES)).replace(second=0, microsecond=0)
    tick -= timedelta(minutes=tick.minute % TICK_MINUTES)

    if daily_moment <= tick:
        return daily_moment, daily_action
    return tick, "tick"


def _generate():
    from social.services.tiktok_publish import build_final_video, cleanup_old_media
    from social.services.tiktok_rotation import pick_product_for_today

    # 04:00 is the maintenance slot: yesterday's networks have long finished
    # fetching, so their files can go before we render a new one.
    removed = cleanup_old_media()

    # Checked before the day's work, not after: a dead token found now leaves
    # the whole day to fix it, rather than surfacing at 18:00 when the post
    # has already failed.
    try:
        _check_tokens()
    except Exception as exc:
        logger.warning("token health check failed: %s", exc)

    # Read yesterday's counters before rendering today's video. Ordering is
    # not cosmetic: build_final_video is the slow, failure-prone step, and a
    # crash there must not cost the day its metrics.
    try:
        collected = _collect_metrics()
    except Exception as exc:
        logger.warning("metrics collection failed: %s", exc)
        collected = "metrics failed"

    # Shop work in the social scheduler, deliberately. This is the only daemon
    # that wakes daily, and the project's norm — stated in
    # ga4_weekly_scheduler — is to piggy-back rather than run another
    # container on a two-core droplet. Before the video, so a render failure
    # does not swallow the day's invitations.
    try:
        invites = _send_review_requests()
    except Exception as exc:
        logger.warning("review requests failed: %s", exc)
        invites = "review requests failed"

    pick = pick_product_for_today()
    path = build_final_video(pick)
    return (
        f"pick #{pick.pk} ({pick.product}) -> {path} "
        f"(cleaned {removed} old files, {collected}, {invites})"
    )


def _send_review_requests():
    from order.review_request import send_due

    sent = send_due()
    return f"review invites: {sent}"


def _collect_metrics():
    """
    Snapshot the recent videos, and on Mondays send the digest.

    Weekly rather than daily because a single day's numbers on a young account
    are noise — one video per network, often single-digit views. Seven days is
    the shortest window where "which network works" is a real question.
    """
    from social.services.video_metrics import collect_once, report_weekly

    written = collect_once()
    if datetime.now(KYIV).weekday() == 0:
        try:
            if report_weekly():
                return f"metrics: {written} read, digest sent"
        except Exception as exc:
            logger.warning("weekly digest failed: %s", exc)
    return f"metrics: {written} read"


def _publish():
    from social.services.tiktok_publish import publish_pick
    from social.services.tiktok_rotation import todays_pick

    pick = todays_pick()
    if pick is None:
        return "nothing prepared for today"
    result = publish_pick(pick)
    return f"pick #{pick.pk}: {result}"


def _check_tokens():
    from social.services.token_health import format_report, run_and_report

    report = run_and_report()
    return format_report(report).splitlines()[0]


def _publish_due():
    """
    Release any network whose stagger slot has arrived.

    A no-op on most ticks: publish_pick skips everything already delivered and
    everything not yet due, so this costs one query when there is nothing to do.
    """
    from social.services.tiktok_publish import publish_pick
    from social.services.tiktok_rotation import todays_pick

    pick = todays_pick()
    if pick is None or pick.status == "published":
        return ""
    # A tick may only CONTINUE a rollout the 18:00 slot has started. Before
    # that, the stagger has no anchor: publish_pick would anchor it to "now",
    # TikTok's zero delay would fire immediately, and the whole day would go
    # out right after the 04:00 generation instead of at prime time.
    # Delivery rows are only ever created by publish_pick, so their absence
    # means the 18:00 slot has not run yet. Presence — even all-failed — means
    # the rollout is underway and the tick may retry and release the rest.
    if not pick.deliveries.exists():
        return ""
    result = publish_pick(pick)
    if result.get("already_published"):
        return ""
    fresh = [p for p in result.get("published", []) if "вже було" not in p]
    if not fresh:
        return ""
    return f"released: {', '.join(fresh)}"


def _poll_comments():
    from social.services.youtube_comments import comments_configured, poll_once

    if not comments_configured():
        return "youtube comments: no API key, skipped"
    return f"youtube comments: {poll_once()} alert(s)"


def _tick():
    """Ten-minute heartbeat: release due networks, poll comments on the hour."""
    parts = []
    try:
        released = _publish_due()
        if released:
            parts.append(released)
    except Exception as exc:
        parts.append(f"publish_due failed: {exc}")

    if datetime.now(KYIV).minute < TICK_MINUTES:
        try:
            parts.append(_poll_comments())
        except Exception as exc:
            parts.append(f"poll failed: {exc}")

    return " | ".join(parts) or "nothing to do"


ACTIONS = {
    "generate": _generate,
    "publish": _publish,
    "tick": _tick,
}


class Command(BaseCommand):
    help = "Daemon: TikTok generate at 04:00 and publish at 18:00 Europe/Kyiv"

    def handle(self, *args, **options):
        self.stdout.write(
            f"tiktok-scheduler started (Europe/Kyiv, "
            f"generate {GENERATE_HOUR:02d}:00, publish {PUBLISH_HOUR:02d}:00, "
            f"tick {TICK_MINUTES}m)"
        )
        while True:
            now = datetime.now(KYIV)
            target, action = next_run(now)
            wait = max((target - now).total_seconds(), 1.0)
            self.stdout.write(f"sleep {int(wait)}s until {target.isoformat()} [{action}]")

            end = time.time() + wait
            while time.time() < end:
                time.sleep(min(3600.0, max(end - time.time(), 0.5)))

            self.stdout.write(f"running {action}…")
            try:
                self.stdout.write(str(ACTIONS[action]()))
            except Exception as exc:
                # publish_pick already alerts Telegram and marks the pick, so
                # here it is enough to survive and wait for the next slot.
                self.stderr.write(f"{action} failed: {exc}")

            # The hourly poll must not eat its own slot: a 90s cooldown after
            # a poll that ran at :00 is harmless, but sleeping it before
            # recomputing the next hour would be wasteful on the daily slots.
            time.sleep(COOLDOWN_SEC if action != "tick" else 5)
