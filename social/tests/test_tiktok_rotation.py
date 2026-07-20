"""Tests: TikTok daily product rotation without repeats."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from catalog.models import Product, ProductImage
from social.models import TikTokDailyPick
from social.services.tiktok_rotation import (
    NoEligibleProducts,
    current_cycle,
    eligible_products,
    mark_failed,
    mark_published,
    pending_generated_pick,
    pick_product_for_today,
    remaining_products,
    rotation_status,
    todays_pick,
)

PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
)


def _product(title: str, *, with_ai_image: bool = True) -> Product:
    product = Product.objects.create(title=title, slug=title.lower().replace(" ", "-"))
    ProductImage.objects.create(
        product=product,
        image=SimpleUploadedFile(f"{product.slug}.gif", PIXEL, content_type="image/gif"),
        is_ai=with_ai_image,
    )
    return product


class PoolTests(TestCase):
    def test_pool_only_contains_products_with_ai_photos(self):
        _product("With AI")
        _product("No AI", with_ai_image=False)
        self.assertEqual(eligible_products().count(), 1)

    def test_product_with_several_ai_photos_counted_once(self):
        product = _product("Multi")
        ProductImage.objects.create(
            product=product,
            image=SimpleUploadedFile("second.gif", PIXEL, content_type="image/gif"),
            is_ai=True,
        )
        self.assertEqual(eligible_products().count(), 1)

    def test_empty_pool_raises(self):
        _product("No AI", with_ai_image=False)
        with self.assertRaises(NoEligibleProducts):
            pick_product_for_today()


class IdempotencyTests(TestCase):
    def setUp(self):
        self.products = [_product(f"Rug {i}") for i in range(3)]

    def test_second_run_same_day_returns_existing_pick(self):
        """A retry must not burn generation budget on another product."""
        first = pick_product_for_today()
        second = pick_product_for_today()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TikTokDailyPick.objects.count(), 1)

    def test_force_creates_another_pick(self):
        first = pick_product_for_today()
        second = pick_product_for_today(force=True)
        self.assertNotEqual(first.pk, second.pk)

    def test_failed_pick_does_not_block_a_new_attempt(self):
        pick = pick_product_for_today()
        mark_failed(pick, "replicate timeout")
        again = pick_product_for_today()
        self.assertNotEqual(pick.pk, again.pk)

    def test_yesterdays_pick_does_not_count_as_todays(self):
        pick = pick_product_for_today()
        pick.picked_at = timezone.now() - timezone.timedelta(days=1)
        pick.save(update_fields=["picked_at"])
        self.assertIsNone(todays_pick())


class SpendingTests(TestCase):
    def setUp(self):
        self.products = [_product(f"Rug {i}") for i in range(3)]

    def test_only_published_retires_a_product(self):
        pick = pick_product_for_today()
        product_id = pick.product_id

        # generated is not spent yet
        self.assertIn(product_id, remaining_products().values_list("pk", flat=True))

        mark_published(pick)
        self.assertNotIn(product_id, remaining_products().values_list("pk", flat=True))

    def test_failed_pick_keeps_product_eligible(self):
        pick = pick_product_for_today()
        product_id = pick.product_id
        mark_failed(pick, "boom")
        self.assertIn(product_id, remaining_products().values_list("pk", flat=True))

    def test_generated_pick_is_offered_for_reuse(self):
        pick = pick_product_for_today()
        self.assertEqual(pending_generated_pick().pk, pick.pk)
        mark_published(pick)
        self.assertIsNone(pending_generated_pick())


class CycleTests(TestCase):
    def setUp(self):
        self.products = [_product(f"Rug {i}") for i in range(3)]

    def _publish_whole_cycle(self):
        seen = []
        for _ in range(len(self.products)):
            pick = pick_product_for_today(force=True)
            mark_published(pick)
            seen.append(pick.product_id)
        return seen

    def test_no_repeats_within_a_cycle(self):
        seen = self._publish_whole_cycle()
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), {p.pk for p in self.products})

    def test_cycle_advances_when_pool_is_exhausted(self):
        self._publish_whole_cycle()
        self.assertEqual(current_cycle(), 1)

        nxt = pick_product_for_today(force=True)
        self.assertEqual(nxt.cycle_number, 2)
        self.assertEqual(current_cycle(), 2)

    def test_new_cycle_makes_every_product_eligible_again(self):
        self._publish_whole_cycle()
        pick_product_for_today(force=True)
        self.assertEqual(remaining_products(2).count(), len(self.products))

    def test_second_cycle_also_avoids_repeats(self):
        self._publish_whole_cycle()
        seen = []
        for _ in range(len(self.products)):
            pick = pick_product_for_today(force=True)
            mark_published(pick)
            seen.append(pick.product_id)
        self.assertEqual(len(seen), len(set(seen)))

    def test_deleted_product_does_not_break_rotation(self):
        """History survives a product deletion; the pick just loses its FK."""
        pick = pick_product_for_today()
        mark_published(pick)
        # admin_objects, not objects: the default manager hides products
        # without stocked attributes, so it would delete nothing here.
        Product.admin_objects.filter(pk=pick.product_id).delete()

        pick.refresh_from_db()
        self.assertIsNone(pick.product_id)
        self.assertEqual(remaining_products().count(), len(self.products) - 1)


class StatusTests(TestCase):
    def test_status_reports_pool_and_progress(self):
        [_product(f"Rug {i}") for i in range(4)]
        mark_published(pick_product_for_today())

        status = rotation_status()
        self.assertEqual(status["cycle"], 1)
        self.assertEqual(status["pool_size"], 4)
        self.assertEqual(status["published_this_cycle"], 1)
        self.assertEqual(status["remaining"], 3)
