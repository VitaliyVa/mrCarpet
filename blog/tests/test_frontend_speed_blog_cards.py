"""Product cards inside articles serve resized WebP, not 200 KB+ originals."""

import os
import shutil
import tempfile
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from PIL import Image

from catalog import thumbnails


class BlogCardThumbnailTests(TestCase):
    def setUp(self):
        from catalog.models import Product, ProductAttribute, Size

        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.root, MEDIA_URL="/media/")
        override.enable()
        self.addCleanup(override.disable)
        thumbnails._memo.clear()

        path = os.path.join(self.root, "products", "rug-speed.png")
        os.makedirs(os.path.dirname(path))
        Image.new("RGB", (1200, 1400), (120, 80, 60)).save(path, format="PNG")

        self.product = Product.objects.create(title="Килим Тест", slug="kylym-speed-blog")
        self.product.image = "products/rug-speed.png"
        self.product.save()
        size = Size.objects.create(title="1.6 x 2.3")
        ProductAttribute.objects.create(product=self.product, size=size, price=1000, quantity=2)

    def _card(self):
        from blog.services.product_cards import build_card

        return build_card(self.product)

    def test_card_uses_480_and_240_thumbnails(self):
        card = self._card()
        self.assertEqual(card["image"], "/media/thumbs/w480/products/rug-speed.webp")
        self.assertEqual(card["image_small"], "/media/thumbs/w240/products/rug-speed.webp")

    def test_big_card_has_srcset_and_mini_card_uses_small(self):
        card = self._card()
        big = render_to_string("includes/blog_products.html", {"cards": [card]})
        self.assertIn(
            'srcset="/media/thumbs/w240/products/rug-speed.webp 240w, '
            '/media/thumbs/w480/products/rug-speed.webp 480w"',
            big,
        )
        mini = render_to_string("includes/blog_products_mini.html", {"cards": [card]})
        self.assertIn('src="/media/thumbs/w240/products/rug-speed.webp"', mini)
        self.assertNotIn("rug-speed.png", big + mini)

    def test_thumbnail_failure_falls_back_to_original(self):
        with patch("catalog.thumbnails.thumbnail_url", side_effect=RuntimeError("boom")):
            card = self._card()
        self.assertEqual(card["image"], "/media/products/rug-speed.png")
        self.assertEqual(card["image_small"], "/media/products/rug-speed.png")
        big = render_to_string("includes/blog_products.html", {"cards": [card]})
        self.assertNotIn("srcset", big)

    def test_missing_file_has_no_image(self):
        self.product.image = "products/nope.png"
        self.product.save()
        card = self._card()
        self.assertIsNone(card["image"])
        self.assertIsNone(card["image_small"])
