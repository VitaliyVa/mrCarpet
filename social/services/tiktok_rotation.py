"""
Daily product rotation for the TikTok auto-poster.

The pool is every product carrying at least one AI interior photo (is_ai),
because those are the frames the video generator works from. A product leaves
the pool for the current cycle only once its video is actually published;
generated-but-unpublished and failed picks stay eligible so a bad run costs a
day, not a product. When the pool empties the cycle number advances and every
product becomes eligible again.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from social.models import TikTokDailyPick

logger = logging.getLogger(__name__)


class NoEligibleProducts(RuntimeError):
    """Raised when no product carries an is_ai photo at all."""


def eligible_products():
    """Products with at least one AI interior photo, newest first."""
    return Product.admin_objects.filter(images__is_ai=True).distinct()


def current_cycle() -> int:
    latest = TikTokDailyPick.objects.order_by("-cycle_number").first()
    return latest.cycle_number if latest else 1


def published_product_ids(cycle: int) -> set[int]:
    return set(
        TikTokDailyPick.objects.filter(
            cycle_number=cycle,
            status=TikTokDailyPick.Status.PUBLISHED,
            product__isnull=False,
        ).values_list("product_id", flat=True)
    )


def remaining_products(cycle: int | None = None):
    """Pool minus everything already published in this cycle."""
    cycle = current_cycle() if cycle is None else cycle
    return eligible_products().exclude(pk__in=published_product_ids(cycle))


def todays_pick(now=None) -> TikTokDailyPick | None:
    """An existing pick for the current day that is not a failed attempt."""
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    return (
        TikTokDailyPick.objects.filter(
            picked_at__date=today,
            status__in=(
                TikTokDailyPick.Status.GENERATED,
                TikTokDailyPick.Status.PUBLISHED,
            ),
        )
        .order_by("-picked_at")
        .first()
    )


def pending_generated_pick() -> TikTokDailyPick | None:
    """
    A video generated earlier but never published.

    Phase 4 reuses this instead of paying for a second generation.
    """
    return (
        TikTokDailyPick.objects.filter(
            status=TikTokDailyPick.Status.GENERATED,
            product__isnull=False,
        )
        .order_by("picked_at")
        .first()
    )


@transaction.atomic
def pick_product_for_today(*, now=None, force: bool = False) -> TikTokDailyPick:
    """
    Return today's pick, creating one when the day has none.

    Idempotent by design: a retry on the same day returns the existing pick
    rather than burning generation budget on a second product. Pass force=True
    to deliberately pick again (admin action, manual re-run).
    """
    now = now or timezone.now()

    if not force:
        existing = todays_pick(now)
        if existing is not None:
            logger.info("TikTok rotation: reusing today's pick #%s", existing.pk)
            return existing

    if not eligible_products().exists():
        raise NoEligibleProducts(
            "No products with an is_ai photo — mark interior shots first"
        )

    cycle = current_cycle()
    candidates = remaining_products(cycle)

    if not candidates.exists():
        cycle += 1
        candidates = remaining_products(cycle)
        logger.info("TikTok rotation: pool exhausted, starting cycle %s", cycle)

    product = candidates.order_by("?").first()
    pick = TikTokDailyPick.objects.create(
        product=product,
        cycle_number=cycle,
        picked_at=now,
        status=TikTokDailyPick.Status.GENERATED,
    )
    logger.info(
        "TikTok rotation: picked product #%s (%s) cycle=%s",
        product.pk,
        product.title[:60],
        cycle,
    )
    return pick


def mark_published(pick: TikTokDailyPick, *, social_post=None) -> TikTokDailyPick:
    """Retire the product for this cycle."""
    pick.status = TikTokDailyPick.Status.PUBLISHED
    pick.error = ""
    if social_post is not None:
        pick.social_post = social_post
    pick.save(update_fields=["status", "error", "social_post", "updated"])
    return pick


def mark_failed(pick: TikTokDailyPick, error: str) -> TikTokDailyPick:
    """Record the failure; the product stays eligible."""
    pick.status = TikTokDailyPick.Status.FAILED
    pick.error = (error or "")[:2000]
    pick.save(update_fields=["status", "error", "updated"])
    return pick


def rotation_status() -> dict:
    cycle = current_cycle()
    pool = eligible_products().count()
    published = len(published_product_ids(cycle))
    return {
        "cycle": cycle,
        "pool_size": pool,
        "published_this_cycle": published,
        "remaining": max(pool - published, 0),
        "todays_pick": todays_pick(),
        "pending_generated": pending_generated_pick(),
    }
