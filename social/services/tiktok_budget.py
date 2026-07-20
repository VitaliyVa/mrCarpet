"""
Hard monthly spending ceiling for TikTok generation.

Every paid call is written to the ledger before it is judged a success, so
retries and outright failures count against the budget too. A guard that only
counted successes would let a handful of bad nights spend several times the
ceiling without ever tripping.

Prices are per Replicate's published rates (2026-07) and are configured rather
than fetched: Replicate does not return a charge on the prediction, so the
ledger records an estimate. Reconcile against the Replicate billing page.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from social.models import SocialSettings, TikTokGenerationSpend

logger = logging.getLogger(__name__)

# USD per second of generated video, by resolution and draft mode.
VIDEO_COST_PER_SEC = {
    ("720p", False): Decimal("0.02"),
    ("720p", True): Decimal("0.005"),
    ("1080p", False): Decimal("0.04"),
    ("1080p", True): Decimal("0.01"),
}
# gpt-image-2 at quality=low, one image. Estimate — verify against billing.
IMAGE_COST = Decimal("0.02")


class TikTokBudgetError(RuntimeError):
    """Raised when a call would exceed the monthly ceiling."""


def video_cost(seconds: int, resolution: str = "720p", draft: bool = False) -> Decimal:
    per_sec = VIDEO_COST_PER_SEC.get(
        (resolution or "720p", bool(draft)), VIDEO_COST_PER_SEC[("720p", False)]
    )
    return (per_sec * Decimal(int(seconds))).quantize(Decimal("0.0001"))


def image_cost() -> Decimal:
    return IMAGE_COST


def month_bounds(now=None):
    now = now or timezone.now()
    local = timezone.localtime(now)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, local


def month_spend(now=None) -> Decimal:
    start, _ = month_bounds(now)
    total = TikTokGenerationSpend.objects.filter(created__gte=start).aggregate(
        total=Sum("cost_usd")
    )["total"]
    return Decimal(total or 0)


def monthly_ceiling() -> Decimal:
    return Decimal(SocialSettings.load().tiktok_monthly_budget_usd or 0)


def remaining_budget(now=None) -> Decimal:
    return monthly_ceiling() - month_spend(now)


def check_affordable(cost: Decimal, *, now=None) -> None:
    """Raise before spending when the call would cross the ceiling."""
    ceiling = monthly_ceiling()
    if ceiling <= 0:
        return  # ceiling disabled
    spent = month_spend(now)
    if spent + cost > ceiling:
        raise TikTokBudgetError(
            f"Monthly TikTok generation budget exceeded: "
            f"spent ${spent} + ${cost} > ${ceiling}"
        )


def record(
    kind: str,
    *,
    cost: Decimal,
    model_name: str = "",
    succeeded: bool = False,
    pick=None,
    note: str = "",
) -> TikTokGenerationSpend:
    """Write the charge to the ledger. Called for failures as well."""
    return TikTokGenerationSpend.objects.create(
        kind=kind,
        model_name=model_name or "",
        cost_usd=cost,
        succeeded=succeeded,
        pick=pick,
        note=(note or "")[:255],
    )


def budget_status(now=None) -> dict:
    ceiling = monthly_ceiling()
    spent = month_spend(now)
    start, _ = month_bounds(now)
    qs = TikTokGenerationSpend.objects.filter(created__gte=start)
    return {
        "month_start": start.date(),
        "ceiling_usd": ceiling,
        "spent_usd": spent,
        "remaining_usd": ceiling - spent,
        "calls": qs.count(),
        "failed_calls": qs.filter(succeeded=False).count(),
    }
