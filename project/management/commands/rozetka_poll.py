"""
Daemon: pull new Rozetka Marketplace orders into our Order table.

Compose service `rozetka-poller` (docker-compose.prod.yml). Credentials and
the poll interval live in the admin (Налаштування Rozetka), read again on
every pass, so changing them needs no restart. Disabled or without
credentials the loop just idles.

    python manage.py rozetka_poll           # loop
    python manage.py rozetka_poll --once    # one pass, for a manual check
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger(__name__)

IDLE_SECONDS = 60


def run_once() -> dict:
    """One pass. Never raises: the loop must outlive a Rozetka or DB hiccup."""
    from project.rozetka_orders import import_new_orders

    try:
        return import_new_orders()
    except Exception as exc:  # import_new_orders already guards; belt and braces
        logger.exception("rozetka poll pass failed")
        return {"created": 0, "skipped": 0, "errors": [str(exc)], "disabled": False}


def next_sleep_seconds() -> int:
    from project.models import RozetkaSettings

    close_old_connections()
    try:
        settings = RozetkaSettings.load()
        return settings.interval_seconds if settings.is_configured else IDLE_SECONDS
    except Exception:
        logger.exception("rozetka: cannot read settings")
        return IDLE_SECONDS
    finally:
        close_old_connections()


def wait_for_telegram(timeout: float = 20.0) -> None:
    """Notifications go out in daemon threads: let them finish before exit."""
    deadline = time.time() + timeout
    for thread in threading.enumerate():
        if thread.name == "telegram-notify":
            thread.join(max(deadline - time.time(), 0.1))


def describe(result: dict) -> str:
    if result.get("disabled"):
        return "disabled"
    text = f"created {result['created']}, skipped {result['skipped']}"
    if result["errors"]:
        text += f", errors: {'; '.join(result['errors'][:3])}"
    return text


class Command(BaseCommand):
    help = "Daemon: import new Rozetka orders every poll_minutes (set in admin)"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one pass and exit")

    def handle(self, *args, **options):
        if options["once"]:
            result = run_once()
            wait_for_telegram()
            self.stdout.write(describe(result))
            return

        self.stdout.write("rozetka-poller started")
        while True:
            result = run_once()
            if result.get("created") or result.get("errors"):
                self.stdout.write(f"{datetime.now():%Y-%m-%d %H:%M} {describe(result)}")
            time.sleep(next_sleep_seconds())
