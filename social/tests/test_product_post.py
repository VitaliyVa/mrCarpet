"""Tests: Product → SocialPost (IG/FB) builder + auto-post."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from catalog.models import Product
from social.models import SocialPost, SocialSettings
from social.services.product_post import (
    AUTO_CAMPAIGN,
    _product_image_names,
    build_product_social_post,
    has_auto_post,
    product_caption_text,
)


def _mock_product_with_sizes():
    size = MagicMock()
    size.title = "80×150"
    attr = MagicMock()
    attr.size_id = 1
    attr.size = size
    attr.get_total_price.return_value = 1000
    attr.in_stock = True
    attr.price = 1000

    out_attr = MagicMock()
    out_attr.size_id = 2
    out_attr.size = MagicMock()
    out_attr.size.title = "120×180"
    out_attr.in_stock = False

    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value = [attr, out_attr]

    product = MagicMock()
    product.title = "Килим тест"
    product.get_size_attrs.return_value = qs
    return product


class ProductCaptionTests(SimpleTestCase):
    def test_caption_title_and_in_stock_sizes(self):
        product = _mock_product_with_sizes()
        caption = product_caption_text(product)
        self.assertIn("Килим тест", caption)
        self.assertIn("Розміри:", caption)
        self.assertIn("80×150 — 1000 грн", caption)
        # out-of-stock розмір не потрапляє в маркетинговий пост
        self.assertNotIn("120×180", caption)

    def test_caption_without_sizes(self):
        product = MagicMock()
        product.title = "Килим без розмірів"
        product.get_size_attrs.side_effect = Exception("no attrs")
        caption = product_caption_text(product)
        self.assertEqual(caption, "Килим без розмірів")


class ProductImageNamesTests(SimpleTestCase):
    def test_main_plus_gallery_dedup(self):
        main = MagicMock()
        main.name = "photos/main.jpg"
        g1 = MagicMock()
        g1.image = MagicMock()
        g1.image.name = "photos/g1.jpg"
        dup = MagicMock()
        dup.image = MagicMock()
        dup.image.name = "photos/main.jpg"  # дубль головного

        product = MagicMock()
        product.image = main
        product.images.order_by.return_value = [g1, dup]

        names = _product_image_names(product)
        self.assertEqual(names, ["photos/main.jpg", "photos/g1.jpg"])

    def test_max_10(self):
        product = MagicMock()
        product.image = None
        gallery = []
        for i in range(15):
            img = MagicMock()
            img.image = MagicMock()
            img.image.name = f"photos/g{i}.jpg"
            gallery.append(img)
        product.images.order_by.return_value = gallery
        self.assertEqual(len(_product_image_names(product)), 10)


class BuildProductSocialPostTests(TestCase):
    def _product(self, with_image=True):
        product = Product.objects.create(title="Килим DB тест")
        if with_image:
            product.image.name = "photos/main.jpg"
            product.save(update_fields=["image"])
        return product

    def test_builds_photos_draft(self):
        product = self._product()
        post = build_product_social_post(product)
        self.assertEqual(post.media_kind, SocialPost.MediaKind.PHOTOS)
        self.assertEqual(post.status, SocialPost.Status.DRAFT)
        self.assertEqual(post.utm_campaign, AUTO_CAMPAIGN)
        self.assertTrue(post.target_instagram)
        self.assertTrue(post.target_facebook)
        self.assertFalse(post.target_tiktok)
        images = list(post.ordered_images())
        self.assertEqual(len(images), 1)
        # файл не копіюється — ім'я вказує на існуючий media-файл товару
        self.assertEqual(images[0].image.name, "photos/main.jpg")
        self.assertIn("Килим DB тест", post.caption)

    def test_no_photos_raises(self):
        # без with_image лишається default-заглушка products/default.png —
        # вона не контент, тому "фото немає"
        product = self._product(with_image=False)
        with self.assertRaises(ValueError):
            build_product_social_post(product)

    def test_has_auto_post_idempotency(self):
        product = self._product()
        self.assertFalse(has_auto_post(product.pk))
        post = build_product_social_post(product)
        self.assertTrue(has_auto_post(product.pk))
        # failed не блокує повторний авто-пост
        post.status = SocialPost.Status.FAILED
        post.save(update_fields=["status"])
        self.assertFalse(has_auto_post(product.pk))


class ProductSignalTests(TestCase):
    @patch("social.services.product_post.enqueue_product_meta_post")
    @patch("social.services.meta.meta_configured", return_value=True)
    def test_signal_fires_when_enabled(self, _cfg, mock_enqueue):
        settings_obj = SocialSettings.load()
        settings_obj.auto_post_new_products_meta = True
        settings_obj.save()
        product = Product.objects.create(title="Signal тест")
        mock_enqueue.assert_called_once_with(product.pk)

    @patch("social.services.product_post.enqueue_product_meta_post")
    def test_signal_silent_when_disabled(self, mock_enqueue):
        settings_obj = SocialSettings.load()
        settings_obj.auto_post_new_products_meta = False
        settings_obj.save()
        Product.objects.create(title="Signal off тест")
        mock_enqueue.assert_not_called()

    @patch("social.services.product_post.enqueue_product_meta_post")
    @patch("social.services.meta.meta_configured", return_value=False)
    def test_signal_silent_when_meta_not_configured(self, _cfg, mock_enqueue):
        settings_obj = SocialSettings.load()
        settings_obj.auto_post_new_products_meta = True
        settings_obj.save()
        Product.objects.create(title="Signal no-config тест")
        mock_enqueue.assert_not_called()
