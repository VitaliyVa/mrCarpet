"""
Daemon: every 5 minutes release scheduled SocialPosts whose time has come.

Its own small compose service (content-scheduler) because the other daemons
do not fit: tiktok-daily is paused behind an opt-in profile, and ga4-weekly
sleeps a whole week between runs. Articles need no job here at all: a
scheduled article becomes public by its published_at alone.

    python manage.py content_scheduler          # loop
    python manage.py content_scheduler --once   # one pass, for a manual check
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger(__name__)

KYIV = ZoneInfo("Europe/Kyiv")
TICK_MINUTES = 5


def next_tick(now: datetime | None = None) -> datetime:
    """Next wall-clock multiple of TICK_MINUTES, so 18:00 posts go out at 18:00."""
    now = (now or datetime.now(KYIV)).astimezone(KYIV)
    tick = (now + timedelta(minutes=TICK_MINUTES)).replace(second=0, microsecond=0)
    return tick - timedelta(minutes=tick.minute % TICK_MINUTES)


def run_once() -> str:
    """One pass. Never raises: the loop must outlive a Meta or DB hiccup."""
    close_old_connections()
    try:
        from social.services.scheduled import release_due_posts

        lines = release_due_posts()
    except Exception as exc:
        logger.exception("content scheduler pass failed")
        return f"release failed: {exc}"
    finally:
        close_old_connections()
    return "; ".join(lines) if lines else "nothing due"


class Command(BaseCommand):
    help = "Daemon: publish scheduled social posts (article announcements) every 5 minutes"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one pass and exit")

    def handle(self, *args, **options):
        if options["once"]:
            self.stdout.write(run_once())
            return

        self.stdout.write(f"content-scheduler started (Europe/Kyiv, tick {TICK_MINUTES}m)")
        while True:
            now = datetime.now(KYIV)
            target = next_tick(now)
            wait = max((target - now).total_seconds(), 1.0)
            end = time.time() + wait
            while time.time() < end:
                time.sleep(max(end - time.time(), 0.5))
            result = run_once()
            if result != "nothing due":
                self.stdout.write(f"{datetime.now(KYIV):%Y-%m-%d %H:%M} {result}")
            # A few seconds so a fast pass cannot land on the same tick twice.
            time.sleep(5)
