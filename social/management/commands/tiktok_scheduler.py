"""
Daemon: generate the TikTok post at 04:00 Kyiv, publish it at 18:00.

Same shape as ga4_weekly_scheduler — a small compose service rather than a
host crontab, so the schedule lives with the code and survives a redeploy.

The two times are split because the work and the audience want different
hours: two model calls and an ffmpeg render belong on an idle droplet at
night, while the post itself should land when people are actually scrolling.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

KYIV = ZoneInfo("Europe/Kyiv")

GENERATE_HOUR = 4
PUBLISH_HOUR = 18
# A failed run must not spin: back off before the loop looks at the clock again.
COOLDOWN_SEC = 90


def next_run(now: datetime | None = None) -> tuple[datetime, str]:
    """Return the next scheduled moment and which step it is."""
    now = (now or datetime.now(KYIV)).astimezone(KYIV)
    candidates = []
    for day_offset in (0, 1):
        day = now + timedelta(days=day_offset)
        for hour, action in ((GENERATE_HOUR, "generate"), (PUBLISH_HOUR, "publish")):
            moment = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            if moment > now:
                candidates.append((moment, action))
    return min(candidates, key=lambda pair: pair[0])


def _generate():
    from social.services.tiktok_publish import build_final_video
    from social.services.tiktok_rotation import pick_product_for_today

    pick = pick_product_for_today()
    path = build_final_video(pick)
    return f"pick #{pick.pk} ({pick.product}) -> {path}"


def _publish():
    from social.services.tiktok_publish import publish_pick
    from social.services.tiktok_rotation import todays_pick

    pick = todays_pick()
    if pick is None:
        return "nothing prepared for today"
    result = publish_pick(pick)
    return f"pick #{pick.pk}: {result}"


class Command(BaseCommand):
    help = "Daemon: TikTok generate at 04:00 and publish at 18:00 Europe/Kyiv"

    def handle(self, *args, **options):
        self.stdout.write(
            f"tiktok-scheduler started (Europe/Kyiv, "
            f"generate {GENERATE_HOUR:02d}:00, publish {PUBLISH_HOUR:02d}:00)"
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
                runner = _generate if action == "generate" else _publish
                self.stdout.write(str(runner()))
            except Exception as exc:
                # publish_pick already alerts Telegram and marks the pick, so
                # here it is enough to survive and wait for the next slot.
                self.stderr.write(f"{action} failed: {exc}")

            time.sleep(COOLDOWN_SEC)
