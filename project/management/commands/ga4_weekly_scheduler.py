"""
Loop: every Monday 10:00 Europe/Kyiv run send_weekly_ga4_report.

Deployed as a small docker service (same pattern as certbot-renew).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from project.ga4_telegram_report import send_weekly_ga4_report

KYIV = ZoneInfo("Europe/Kyiv")


def next_monday_10(now: datetime | None = None) -> datetime:
    """Return next Monday 10:00 Europe/Kyiv (strictly in the future)."""
    now = now or datetime.now(KYIV)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KYIV)
    else:
        now = now.astimezone(KYIV)
    days_ahead = (0 - now.weekday()) % 7
    target = (now + timedelta(days=days_ahead)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    if target <= now:
        target += timedelta(days=7)
    return target


def seconds_until_next_monday_10(now: datetime | None = None) -> float:
    return max((next_monday_10(now) - (now or datetime.now(KYIV)).astimezone(KYIV)).total_seconds(), 1.0)


class Command(BaseCommand):
    help = "Daemon: weekly GA4 Telegram report every Monday 10:00 Kyiv"

    def handle(self, *args, **options):
        self.stdout.write("ga4-weekly-scheduler started (Europe/Kyiv)")
        while True:
            now = datetime.now(KYIV)
            target = next_monday_10(now)
            wait = max((target - now).total_seconds(), 1.0)
            self.stdout.write(f"sleep {int(wait)}s until {target.isoformat()}")
            end = time.time() + wait
            while time.time() < end:
                time.sleep(min(3600.0, max(end - time.time(), 0.5)))
            self.stdout.write("running weekly report…")
            try:
                result = send_weekly_ga4_report()
                self.stdout.write(str(result))
            except Exception as exc:
                self.stderr.write(f"weekly report failed: {exc}")

            # Тижневе прибирання покинутих анонімних кошиків.
            # Окремий сервіс під це не заводимо — цей демон і так прокидається.
            try:
                from cart.management.commands.cleanup_carts import cleanup_carts

                stats = cleanup_carts()
                self.stdout.write(f"carts cleanup: {stats}")
            except Exception as exc:
                self.stderr.write(f"carts cleanup failed: {exc}")

            # Стаття тижня — теж сюди, за тим самим принципом: це єдиний
            # тижневий демон. Генерує ЧЕРНЕТКУ і пінгує в Telegram; публікує
            # людина. Автопублікація масово згенерованого — це scaled content
            # abuse, і штраф прилітає на домен, а не на пост.
            try:
                from blog.services.weekly_topic import generate_next

                result = generate_next()
                self.stdout.write(f"weekly article: {result}")
            except Exception as exc:
                self.stderr.write(f"weekly article failed: {exc}")

            time.sleep(90)
