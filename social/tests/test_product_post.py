"""Tests: Product → SocialPost (IG/FB) builder + auto-post."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from catalog.models import Product
from social.models import SocialPost, SocialSettings
from social.services.post_content import FRIENDLY_OUTRO
from social.services.product_post import (
    AUTO_CAMPAIGN,
    _product_image_names,
    build_product_social_post,
    has_auto_post,
    product_caption_text,
)


def _bare_mock_product(title):
    """Product-мок без кастому/характеристик/кольору — чистий фон."""
    product = MagicMock()
    product.title = title
    product.get_absolute_url.return_value = "/catalog/product/test/"
    product.product_attr.filter.return_value.first.return_value = None
    product.product_specs.select_related.side_effect = Exception("no specs")
    product.active_color_id = None
    product.get_default_size_attr.return_value = None
    return product


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
    out_attr.get_total_price.return_value = 1500
    out_attr.in_stock = False

    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value = [attr, out_attr]

    product = _bare_mock_product("Килим тест")
    product.get_size_attrs.return_value = qs
    return product


class ProductCaptionTests(SimpleTestCase):
    def test_caption_title_and_sizes_mirror_tg(self):
        product = _mock_product_with_sizes()
        caption = product_caption_text(product)
        self.assertIn("✨ Килим тест", caption)
        self.assertIn("🏷 Розміри та ціни:", caption)
        self.assertIn("80×150 — 1000 грн", caption)
        # out-of-stock розмір показується з поміткою
        self.assertIn("немає", caption)
        self.assertIn("120×180", caption)
        # дружній фінал
        self.assertIn("💬", caption)
        # url для IG/FB не включається (його додає build_caption)
        self.assertNotIn("http", caption)

    def test_caption_specs(self):
        product = _mock_product_with_sizes()
        spec = MagicMock()
        spec.specification.title = "Матеріал"
        spec.spec_value.title = "Поліпропілен"
        product.product_specs.select_related.side_effect = None
        product.product_specs.select_related.return_value.order_by.return_value = [spec]
        caption = product_caption_text(product)
        self.assertIn("🧵 Характеристики:", caption)
        self.assertIn("• Матеріал: Поліпропілен", caption)

    def test_caption_never_shows_color(self):
        # колір не показуємо ніколи (вимога користувача)
        product = _mock_product_with_sizes()
        product.active_color_id = 1
        product.active_color.title = "Синій"
        caption = product_caption_text(product)
        self.assertNotIn("🎨", caption)
        self.assertNotIn("Синій", caption)

    def test_caption_price_fallback_without_sizes(self):
        product = _bare_mock_product("Килим без розмірів")
        product.get_size_attrs.side_effect = Exception("no attrs")
        default_attr = MagicMock()
        default_attr.custom_attribute = False
        default_attr.get_total_price.return_value = 2500
        product.get_default_size_attr.return_value = default_attr
        caption = product_caption_text(product)
        self.assertIn("Килим без розмірів", caption)
        self.assertIn("🏷 Ціна: 2500 грн", caption)

    def test_caption_custom_size_line(self):
        product = _bare_mock_product("Килим на замовлення")
        product.get_size_attrs.side_effect = Exception("no attrs")
        custom = MagicMock()
        custom.custom_price = 500
        product.product_attr.filter.return_value.first.return_value = custom
        caption = product_caption_text(product)
        self.assertIn("📏 Індивідуальний розмір — від 500 грн/м²", caption)

    def test_caption_ar_teaser_when_ready(self):
        product = _mock_product_with_sizes()
        product.ar_status = "ready"
        product.ar_texture = "textures/x.png"
        caption = product_caption_text(product)
        self.assertIn("Приміряйте цей килим у себе вдома", caption)

    def test_caption_no_ar_teaser_when_not_ready(self):
        product = _mock_product_with_sizes()
        product.ar_status = "none"
        product.ar_texture = None
        caption = product_caption_text(product)
        self.assertNotIn("Приміряйте", caption)

    def test_viber_caption_skips_ar_teaser(self):
        from social.services.post_content import build_product_content, render_plain

        product = _mock_product_with_sizes()
        product.ar_status = "ready"
        product.ar_texture = "textures/x.png"
        text = render_plain(
            build_product_content(product),
            max_len=768,
            with_url=True,
            include_ar=False,
        )
        self.assertNotIn("Приміряйте", text)

    def test_caption_bare_title_when_nothing_else(self):
        product = _bare_mock_product("Килим голий")
        product.get_size_attrs.side_effect = Exception("no attrs")
        caption = product_caption_text(product)
        self.assertIn("✨ Килим голий", caption)
        self.assertIn(FRIENDLY_OUTRO, caption)


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
