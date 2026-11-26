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
        result = import_new_orders()
    except Exception as exc:  # import_new_orders already guards; belt and braces
        logger.exception("rozetka poll pass failed")
        result = {"created": 0, "skipped": 0, "errors": [str(exc)], "disabled": False}
    if result.get("disabled"):
        return result
    extra_errors = []
    for name, func in _extra_steps():
        try:
            step = func() or {}
        except Exception as exc:
            logger.exception("rozetka %s step failed", name)
            step = {"errors": [str(exc)]}
        result[name] = step
        extra_errors.extend(f"{name}: {e}" for e in step.get("errors") or [])
    if extra_errors:
        result["errors"] = list(result.get("errors") or []) + extra_errors
        _append_error(extra_errors)
    return result


def _extra_steps():
    """Steps after the order import; each owns its module and never raises."""
    from project.models import RozetkaSettings
    from project.rozetka_messages import notify_new_messages
    from project.rozetka_stock import sync_stock

    settings = RozetkaSettings.load()
    steps = []
    if settings.notify_messages:
        steps.append(("messages", notify_new_messages))
    if settings.sync_stock:
        steps.append(("stock", sync_stock))
    return steps


def _append_error(errors: list[str]) -> None:
    """import_new_orders wrote last_error for orders; add the other steps' errors."""
    from project.models import RozetkaSettings

    try:
        settings = RozetkaSettings.load()
        text = "; ".join(p for p in [settings.last_error] + errors[:3] if p)
        RozetkaSettings.objects.filter(pk=settings.pk).update(last_error=text[:2000])
    except Exception:
        logger.exception("rozetka: could not save step errors")


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
