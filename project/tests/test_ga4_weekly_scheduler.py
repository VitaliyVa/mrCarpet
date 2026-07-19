"""Weekly scheduler helpers."""

from __future__ import annotations

from datetime import datetime
from unittest import TestCase
from zoneinfo import ZoneInfo

from project.management.commands.ga4_weekly_scheduler import next_monday_10

KYIV = ZoneInfo("Europe/Kyiv")


class Ga4WeeklySchedulerTests(TestCase):
    def test_wednesday_to_monday(self):
        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=KYIV)  # Wed
        nxt = next_monday_10(now)
        self.assertEqual(nxt.weekday(), 0)
        self.assertEqual(nxt.hour, 10)
        self.assertEqual(nxt.day, 20)  # next Monday

    def test_monday_before_10_same_day(self):
        now = datetime(2026, 7, 20, 9, 0, 0, tzinfo=KYIV)
        nxt = next_monday_10(now)
        self.assertEqual(nxt.day, 20)
        self.assertEqual(nxt.hour, 10)

    def test_monday_after_10_next_week(self):
        now = datetime(2026, 7, 20, 10, 0, 1, tzinfo=KYIV)
        nxt = next_monday_10(now)
        self.assertEqual(nxt.day, 27)
