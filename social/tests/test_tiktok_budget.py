"""Tests: monthly spending ceiling for TikTok generation."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from social.models import SocialSettings, TikTokGenerationSpend
from social.services import tiktok_budget
from social.services.tiktok_budget import (
    TikTokBudgetError,
    budget_status,
    check_affordable,
    month_spend,
    record,
    remaining_budget,
    video_cost,
)


def _ceiling(value):
    social = SocialSettings.load()
    social.tiktok_monthly_budget_usd = Decimal(str(value))
    social.save()


class CostTests(TestCase):
    def test_720p_matches_published_rate(self):
        self.assertEqual(video_cost(6, "720p", False), Decimal("0.1200"))

    def test_draft_is_four_times_cheaper(self):
        self.assertEqual(video_cost(6, "720p", True), Decimal("0.0300"))

    def test_1080p_doubles_the_price(self):
        self.assertEqual(video_cost(6, "1080p", False), Decimal("0.2400"))

    def test_unknown_resolution_falls_back_to_720p(self):
        self.assertEqual(video_cost(6, "4k", False), Decimal("0.1200"))


class CeilingTests(TestCase):
    def setUp(self):
        _ceiling(5)

    def test_spend_accumulates(self):
        record("video", cost=Decimal("0.12"), succeeded=True)
        record("video", cost=Decimal("0.12"), succeeded=True)
        self.assertEqual(month_spend(), Decimal("0.24"))

    def test_failed_calls_still_count(self):
        """Retries cost money; a guard that ignored them would overspend."""
        record("video", cost=Decimal("0.12"), succeeded=False)
        record("video", cost=Decimal("0.12"), succeeded=False)
        record("video", cost=Decimal("0.12"), succeeded=True)
        self.assertEqual(month_spend(), Decimal("0.36"))

    def test_call_within_budget_is_allowed(self):
        record("video", cost=Decimal("4.00"), succeeded=True)
        check_affordable(Decimal("0.12"))  # must not raise

    def test_call_crossing_ceiling_raises_before_spending(self):
        record("video", cost=Decimal("4.95"), succeeded=True)
        with self.assertRaises(TikTokBudgetError):
            check_affordable(Decimal("0.12"))

    def test_zero_ceiling_disables_the_guard(self):
        _ceiling(0)
        record("video", cost=Decimal("999"), succeeded=True)
        check_affordable(Decimal("100"))  # must not raise

    def test_previous_month_does_not_count(self):
        old = record("video", cost=Decimal("4.90"), succeeded=True)
        TikTokGenerationSpend.objects.filter(pk=old.pk).update(
            created=timezone.now() - timezone.timedelta(days=45)
        )
        self.assertEqual(month_spend(), Decimal("0"))
        check_affordable(Decimal("0.12"))

    def test_remaining_budget_reflects_spend(self):
        record("video", cost=Decimal("1.50"), succeeded=True)
        self.assertEqual(remaining_budget(), Decimal("3.50"))

    def test_status_counts_failures_separately(self):
        record("video", cost=Decimal("0.12"), succeeded=True)
        record("image", cost=Decimal("0.02"), succeeded=False)
        status = budget_status()
        self.assertEqual(status["calls"], 2)
        self.assertEqual(status["failed_calls"], 1)
        self.assertEqual(status["spent_usd"], Decimal("0.14"))


class MonthlyProjectionTests(TestCase):
    def test_daily_6s_video_fits_the_five_dollar_ceiling(self):
        """31 days x 6s at 720p must stay under the configured ceiling."""
        _ceiling(5)
        monthly = video_cost(6, "720p", False) * 31
        self.assertLess(monthly, Decimal("5"))

    def test_1080p_would_break_the_ceiling(self):
        monthly = video_cost(6, "1080p", False) * 31
        self.assertGreater(monthly, Decimal("5"))


class GuardIntegrationTests(TestCase):
    """The guard must stop the call before any money is spent."""

    def setUp(self):
        _ceiling(5)
        record("video", cost=Decimal("4.99"), succeeded=True)

    def test_video_generation_refuses_when_over_budget(self):
        from social.models import TikTokDailyPick
        from social.services.tiktok_video import generate_video_for_pick

        social = SocialSettings.load()
        social.tiktok_auto_enabled = True
        social.save()

        pick = TikTokDailyPick.objects.create(product=None)
        with patch.object(tiktok_budget, "check_affordable", side_effect=TikTokBudgetError("over")):
            with self.assertRaises(Exception):
                generate_video_for_pick(pick)
