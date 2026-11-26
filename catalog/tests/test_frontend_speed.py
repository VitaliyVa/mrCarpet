"""Lighthouse mobile findings on listing pages and the product page.

* The first cards of a category are the mobile LCP: they must not be lazy.
* Page bundles load with ``defer`` so they never block the first paint.
* Guide card text on category pages passes WCAG AA contrast (4.5:1).
"""

import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import TestCase


def _cards(html):
    return html.split('<div class="cart_item" ')[1:]


def _card_img(card):
    m = re.search(r'<div class="cart_item_img">\s*<img(.*?)/>', card, re.S)
    return m.group(1) if m else ""


class ListingEagerCardsTests(TestCase):
    def setUp(self):
        from catalog.models import Product, ProductAttribute, ProductCategory, Size

        self.category = ProductCategory.objects.create(title="Швидка", slug="shvydka")
        size = Size.objects.create(title="1 x 2")
        for i in range(5):
            p = Product.objects.create(title=f"Килим {i}", slug=f"kylym-speed-{i}")
            ProductAttribute.objects.create(product=p, size=size, price=100 + i, quantity=1)
            p.categories.add(self.category)

    def test_first_two_category_cards_are_eager_with_high_priority(self):
        html = self.client.get(f"/catalog/categorie/{self.category.slug}/").content.decode()
        imgs = [_card_img(c) for c in _cards(html)]
        self.assertEqual(len(imgs), 5)
        for img in imgs[:2]:
            self.assertIn('loading="eager"', img)
            self.assertIn('fetchpriority="high"', img)
            self.assertNotIn('loading="lazy"', img)
        for img in imgs[2:]:
            self.assertIn('loading="lazy"', img)
            self.assertNotIn("fetchpriority", img)

    def test_card_include_is_lazy_by_default(self):
        from catalog.models import Product

        product = Product.objects.get(slug="kylym-speed-0")
        lazy = render_to_string("includes/products.html", {"product": product})
        eager = render_to_string("includes/products.html", {"product": product, "eager": True})
        self.assertIn('loading="lazy"', lazy)
        self.assertNotIn("fetchpriority", lazy)
        self.assertIn('loading="eager" fetchpriority="high"', eager)


class DeferredBundlesTests(TestCase):
    def test_page_bundles_are_deferred(self):
        for template, bundle in (
            ("product.html", "pages/product/index.js"),
            ("about.html", "pages/about/index.js"),
            ("blog_inside.html", "pages/blog_inside/index.js"),
        ):
            text = Path("templates", template).read_text(encoding="utf-8")
            tag = re.search(r"<script[^>]*%s[^>]*>" % re.escape(bundle), text)
            self.assertIsNotNone(tag, template)
            self.assertIn(" defer", tag.group(0), template)


def _luminance(hex_color):
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


class GuideCardContrastTests(TestCase):
    def test_card_text_passes_aa_on_white(self):
        css = Path("static/source/pages/catalog_inside/seo-guides-fix.css").read_text(encoding="utf-8")
        m = re.search(r"\.catalog_seo_guides__card-text\{[^}]*color:#([0-9a-fA-F]{6})", css)
        self.assertIsNotNone(m)
        ratio = (1.0 + 0.05) / (_luminance(m.group(1)) + 0.05)
        self.assertGreaterEqual(ratio, 4.5)
