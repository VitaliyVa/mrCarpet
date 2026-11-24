"""Discounts: «Акції» page, header link, JSON-LD strike-through, feed dates.

Audit 24.11.2026: /catalog/stock/ showed the plain catalogue (T7); the
discounted Offer had no StrikethroughPrice and the sale end date was used
nowhere (SD5).
"""

import json
import re
from datetime import timedelta

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from catalog.models import Product, ProductAttribute, ProductCategory, ProductSale, Size
from catalog.promotions import (
    PROMO_CACHE_KEY,
    active_sale_windows,
    discounted_in_stock_products,
    has_promo,
    is_real_discount,
)

SITE = "https://mrcarpet24.com"


def _robots(html):
    m = re.search(r'<meta name="robots" content="([^"]*)"', html)
    return m and m.group(1)


def _canonical(html):
    m = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return m and m.group(1)


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = ProductCategory.objects.create(title="Турецькі", slug="turetski")
        cls.small = Size.objects.create(title="0.6 x 1.0")
        cls.big = Size.objects.create(title="2.0 x 3.0")
        cls.plain = cls._product("Килим звичайний", "plain", [(cls.small, 1000, None, 3)])

    @classmethod
    def _product(cls, title, slug, sizes):
        p = Product.objects.create(title=title, slug=slug, image="products/x.jpg")
        for size, price, discount, qty in sizes:
            ProductAttribute.objects.create(
                product=p, size=size, price=price, discount=discount, quantity=qty
            )
        p.categories.add(cls.cat)
        return p

    def setUp(self):
        cache.delete(PROMO_CACHE_KEY)


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
class EmptyStockTests(_Base):
    def test_page_is_friendly_and_noindex(self):
        # a discount on a size that is sold out does not count
        self._product("Килим розпроданий", "sold", [(self.small, 1000, 20, 0)])
        html = self.client.get("/catalog/stock/").content.decode()
        self.assertEqual(_robots(html), "noindex, follow")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/stock/")
        self.assertIn("Зараз акцій немає", html)
        self.assertIn(f'href="{self.cat.get_absolute_url()}"', html)
        self.assertIn('href="/catalog/collection/"', html)
        self.assertNotIn("data-catalog-product-id", html)

    def test_copy_has_no_long_dashes(self):
        from pathlib import Path

        from django.conf import settings

        text = (Path(settings.BASE_DIR) / "templates" / "stock.html").read_text(encoding="utf-8")
        self.assertNotIn("—", text)
        self.assertNotIn("–", text)

    def test_header_hides_link(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn('href="/catalog/stock/"', html)
        self.assertFalse(has_promo())

    def test_not_in_sitemap(self):
        from project.sitemaps import StaticViewSitemap

        items = StaticViewSitemap().items()
        self.assertIn("all_collection", items)
        self.assertNotIn("stock", items)


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
class StockWithDiscountTests(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # discount on the second size only: the flag used to miss it
        cls.sale = cls._product(
            "Килим зі знижкою", "sale",
            [(cls.small, 1000, None, 2), (cls.big, 4000, 25, 1)],
        )

    def test_lists_only_discounted_in_stock(self):
        resp = self.client.get("/catalog/stock/")
        html = resp.content.decode()
        self.assertEqual([p.pk for p in resp.context["products"]], [self.sale.pk])
        self.assertEqual(_robots(html), "index, follow, max-image-preview:large, max-snippet:-1")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/stock/")
        self.assertIn("Акції на килими", html)
        self.assertNotIn("Зараз акцій немає", html)

    def test_header_shows_link_and_caches(self):
        html = self.client.get("/").content.decode()
        self.assertEqual(html.count('href="/catalog/stock/"'), 2)
        self.assertTrue(cache.get(PROMO_CACHE_KEY))
        # a saved size clears the cached answer at once
        ProductAttribute.objects.filter(product=self.sale, discount=25).get().save()
        self.assertIsNone(cache.get(PROMO_CACHE_KEY))

    def test_has_discount_flag_sees_any_size(self):
        self.sale.refresh_from_db()
        self.assertTrue(self.sale.has_discount)

    def test_sitemap_lists_stock(self):
        from project.sitemaps import StaticViewSitemap

        self.assertIn("stock", StaticViewSitemap().items())

    def test_shows_sale_end_from_main_sale(self):
        sale = ProductSale.objects.create(
            date_end=timezone.now() + timedelta(days=3), main_sale=True
        )
        sale.products.add(self.sale)
        resp = self.client.get("/catalog/stock/")
        self.assertEqual(resp.context["sale_end"], sale.date_end)
        self.assertIn("Акція діє до", resp.content.decode())

    def test_card_crosses_out_only_real_discount(self):
        html = self.client.get("/catalog/collection/").content.decode()
        plain_card = html[html.index(f'data-catalog-product-id="{self.plain.pk}"'):]
        plain_card = plain_card[: plain_card.index("cart_item_title")]
        self.assertNotIn("cart_item_old_price-value", plain_card)

    def test_real_discount_helper(self):
        attrs = {a.discount: a for a in self.sale.product_attr.all()}
        self.assertTrue(is_real_discount(attrs[25]))
        self.assertFalse(is_real_discount(attrs[None]))
        self.assertEqual(list(discounted_in_stock_products()), [self.sale])


@override_settings(SITE_URL=SITE)
class SaleStructuredDataTests(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sale = cls._product(
            "Килим зі знижкою", "sale-ld",
            [(cls.small, 1000, None, 2), (cls.big, 4000, 25, 1)],
        )
        cls.big_attr = cls.sale.product_attr.get(discount=25)
        cls.small_attr = cls.sale.product_attr.get(discount=None)

    def _graph(self, product, attr=None):
        from project.seo_jsonld import product_graph

        request = RequestFactory().get(product.get_absolute_url())
        return product_graph(request, product, images=[], selected_attr=attr)

    def _offers(self, graph):
        return {v["sku"]: v["offers"] for v in graph.get("hasVariant", []) if "sku" in v}

    def test_strikethrough_only_on_discounted_size(self):
        offers = self._offers(self._graph(self.sale))
        big = offers[f"{self.sale.pk}-{self.big_attr.pk}"]
        small = offers[f"{self.sale.pk}-{self.small_attr.pk}"]
        self.assertEqual(big["price"], 3000)
        self.assertEqual(
            big["priceSpecification"],
            {
                "@type": "UnitPriceSpecification",
                "priceType": "https://schema.org/StrikethroughPrice",
                "price": 4000,
                "priceCurrency": "UAH",
            },
        )
        self.assertNotIn("priceSpecification", small)
        json.dumps(big)  # serialisable

    def test_price_valid_until_is_sale_end(self):
        end = timezone.now() + timedelta(days=4)
        sale = ProductSale.objects.create(date_end=end)
        sale.products.add(self.sale)
        offers = self._offers(self._graph(self.sale))
        big = offers[f"{self.sale.pk}-{self.big_attr.pk}"]
        small = offers[f"{self.sale.pk}-{self.small_attr.pk}"]
        self.assertEqual(big["priceValidUntil"], timezone.localtime(end).date().isoformat())
        # the full-price size keeps the usual window
        self.assertNotEqual(small["priceValidUntil"], big["priceValidUntil"])
        # the ?size= page of the discounted size says the same
        node = self._graph(self.sale, attr=self.big_attr)
        self.assertEqual(node["offers"]["priceValidUntil"], big["priceValidUntil"])
        self.assertEqual(node["offers"]["priceSpecification"]["price"], 4000)

    def test_finished_sale_is_ignored(self):
        sale = ProductSale.objects.create(date_end=timezone.now() - timedelta(days=1))
        sale.products.add(self.sale)
        self.assertEqual(active_sale_windows([self.sale.pk]), {})
        offers = self._offers(self._graph(self.sale))
        big = offers[f"{self.sale.pk}-{self.big_attr.pk}"]
        self.assertGreater(big["priceValidUntil"], timezone.now().date().isoformat())

    def test_feed_effective_date_only_for_running_sale(self):
        from project.merchant_feed import build_items, feed_products

        end = timezone.now() + timedelta(days=4)
        sale = ProductSale.objects.create(date_end=end)
        sale.products.add(self.sale)
        items = {i["id"]: i for i in build_items(feed_products())}
        big = items[f"{self.sale.pk}-{self.big_attr.pk}"]
        small = items[f"{self.sale.pk}-{self.small_attr.pk}"]
        self.assertEqual(big["sale_price"], "3000.00 UAH")
        start_s, end_s = big["sale_price_effective_date"].split("/")
        self.assertEqual(end_s, timezone.localtime(end).isoformat(timespec="minutes"))
        self.assertLess(start_s, end_s)
        self.assertNotIn("sale_price_effective_date", small)

        ProductSale.objects.filter(pk=sale.pk).update(date_end=timezone.now() - timedelta(hours=1))
        items = {i["id"]: i for i in build_items(feed_products())}
        big = items[f"{self.sale.pk}-{self.big_attr.pk}"]
        self.assertEqual(big["sale_price"], "3000.00 UAH")
        self.assertNotIn("sale_price_effective_date", big)


class HomeSaleBlockTests(_Base):
    def test_finished_main_sale_is_hidden(self):
        sale = ProductSale.objects.create(
            date_end=timezone.now() - timedelta(days=30), main_sale=True
        )
        sale.products.add(self.plain)
        resp = self.client.get("/")
        self.assertEqual(list(resp.context["sale_products"]), [])
        self.assertNotIn('data-ga-list-id="home_sale"', resp.content.decode())

    def test_running_main_sale_is_shown(self):
        sale = ProductSale.objects.create(
            date_end=timezone.now() + timedelta(days=2), main_sale=True
        )
        sale.products.add(self.plain)
        resp = self.client.get("/")
        self.assertEqual([p.pk for p in resp.context["sale_products"]], [self.plain.pk])
        self.assertIn('data-ga-list-id="home_sale"', resp.content.decode())
