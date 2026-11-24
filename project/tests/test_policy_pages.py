"""Delivery / return terms tell one truth everywhere (audit SD1, ads shipping
mismatch, PDP trust lines, contacts page G8).

The delivery page, refund page, FAQ, PDP buy box, checkout, Offer JSON-LD and
the Merchant feed all read project.free_shipping + ShopSettings.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from catalog.models import Product, ProductAttribute, Size
from project.free_shipping import (
    HANDLING_DAYS,
    RETURN_DAYS,
    TRANSIT_DAYS,
    delivery_terms,
    shipping_rate,
)
from project.models import ShopSettings

SITE = "https://mrcarpet24.com"
DASHES = ("—", "–")
G = "{http://base.google.com/ns/1.0}"


def _settings(**kw):
    base = dict(free_shipping_enabled=True, free_shipping_threshold=1499, delivery_from_price=90)
    base.update(kw)
    return SimpleNamespace(**base)


def _main(html: str) -> str:
    """Page body without header/footer (they carry their own copy)."""
    start = html.find('<div class="terms-and-policies__content">')
    if start < 0:
        start = html.find("<main")
    end = html.find("<footer")
    # CSS comments are not customer copy
    return re.sub(r"<style.*?</style>", "", html[start:end], flags=re.S)


class ShippingHelpersTests(SimpleTestCase):
    def test_rate_from_threshold(self):
        s = _settings()
        self.assertEqual(shipping_rate(400, s), 90)
        self.assertEqual(shipping_rate(1499, s), 0)
        self.assertEqual(shipping_rate(5000, s), 0)
        self.assertEqual(shipping_rate(None, s), 0)

    def test_rate_when_free_shipping_off(self):
        s = _settings(free_shipping_enabled=False)
        self.assertEqual(shipping_rate(5000, s), 90)
        self.assertIsNone(shipping_rate(5000, _settings(free_shipping_enabled=False, delivery_from_price=0)))

    def test_terms_texts(self):
        terms = delivery_terms(_settings(free_shipping_threshold=2000))
        self.assertEqual(terms["threshold"], 2000)
        self.assertTrue(terms["free_enabled"])
        self.assertEqual(terms["transit_text"], f"{TRANSIT_DAYS[0]}-{TRANSIT_DAYS[1]} днів")
        self.assertEqual(terms["handling_text"], "до 2 робочих днів")
        self.assertEqual(terms["return_days_text"], "14 днів")
        self.assertFalse(delivery_terms(_settings(free_shipping_enabled=False))["free_enabled"])

    def test_jsonld_uses_the_same_days(self):
        from project.seo_jsonld import MERCHANT_RETURN_DAYS, offer_shipping_details

        self.assertEqual(MERCHANT_RETURN_DAYS, RETURN_DAYS)
        with mock.patch("project.free_shipping.get_shop_settings", return_value=_settings()):
            details = offer_shipping_details(400)
        time = details["deliveryTime"]
        self.assertEqual(
            (time["handlingTime"]["minValue"], time["handlingTime"]["maxValue"]), HANDLING_DAYS
        )
        self.assertEqual(
            (time["transitTime"]["minValue"], time["transitTime"]["maxValue"]), TRANSIT_DAYS
        )

    def test_jsonld_claims_nothing_when_settings_fail(self):
        from project.seo_jsonld import offer_shipping_details

        with mock.patch("project.free_shipping.get_shop_settings", side_effect=RuntimeError):
            self.assertIsNone(offer_shipping_details(400))

    def test_faq_states_threshold_tariff_and_days(self):
        from project.seo_jsonld import get_faq_items

        with mock.patch("project.free_shipping.get_shop_settings", return_value=_settings(free_shipping_threshold=2000)):
            answers = dict(get_faq_items())
        delivery = answers["Які умови доставки?"]
        self.assertIn("Від 2000 грн доставка безкоштовна", delivery)
        self.assertIn("від 90 грн", delivery)
        self.assertIn("1-5 днів", delivery)
        self.assertIn("14 днів", answers["Чи можна повернути килим?"])
        self.assertIn("при отриманні", answers["Як оплатити замовлення?"])
        for text in answers.values():
            for dash in DASHES:
                self.assertNotIn(dash, text)


class SizeCmFilterTests(SimpleTestCase):
    def test_formats_like_the_feed(self):
        from catalog.templatetags.catalog_filters import size_cm

        self.assertEqual(size_cm("2.0х3.0"), "200x300 см")
        self.assertEqual(size_cm("1.2x2.0"), "120x200 см")
        self.assertEqual(size_cm(SimpleNamespace(title="0.6х1.0")), "60x100 см")
        self.assertEqual(size_cm(None), "")


def _product(slug, price, size="2.0х3.0"):
    product = Product.objects.create(
        title=f"Килим {slug}", slug=slug, image="products/x.webp", description="Опис."
    )
    attr = ProductAttribute.objects.create(
        product=product, size=Size.objects.create(title=size), price=price, quantity=2
    )
    return product, attr


class FeedShippingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cheap, _ = _product("kylym-cheap", 600, "0.6х1.0")
        cls.dear, _ = _product("kylym-dear", 2000)

    def _items(self):
        from project.merchant_feed import build_items, feed_products

        return {i["item_group_id"]: i for i in build_items(feed_products())}

    def test_shipping_follows_threshold(self):
        items = self._items()
        cheap = items[str(self.cheap.pk)]["shipping"]
        dear = items[str(self.dear.pk)]["shipping"]
        self.assertEqual(cheap["price"], "90.00 UAH")
        self.assertEqual(dear["price"], "0.00 UAH")
        self.assertEqual(cheap["country"], "UA")
        self.assertEqual(cheap["service"], "Нова Пошта")
        self.assertEqual(
            (cheap["min_transit_time"], cheap["max_transit_time"]), TRANSIT_DAYS
        )

    def test_threshold_read_from_settings(self):
        s = ShopSettings.load()
        s.free_shipping_threshold = 3000
        s.save()
        self.assertEqual(self._items()[str(self.dear.pk)]["shipping"]["price"], "90.00 UAH")

    def test_rendered_xml(self):
        from project.merchant_feed import build_items, feed_products, render_feed

        root = ET.fromstring(render_feed(build_items(feed_products())).encode("utf-8"))
        shipping = root.find(f"channel/item/{G}shipping")
        self.assertIsNotNone(shipping)
        self.assertEqual(shipping.findtext(f"{G}country"), "UA")
        self.assertEqual(shipping.findtext(f"{G}min_handling_time"), "0")
        self.assertEqual(shipping.findtext(f"{G}max_transit_time"), str(TRANSIT_DAYS[1]))


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
class PolicyPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        s = ShopSettings.load()
        s.free_shipping_threshold = 1777  # not the default: proves no hard-coded number
        s.save()

    def get(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, url)
        return resp.content.decode()

    def test_delivery_page_states_the_policy(self):
        html = self.get(reverse("delivery"))
        body = _main(html)
        self.assertIn("Від 1777 грн доставка безкоштовна", body)
        self.assertIn("від 90 грн", body)
        self.assertIn("1-5 днів", body)
        self.assertIn("комісію", body)
        self.assertIn("14 днів", body)
        self.assertNotIn("коштом покупця", body)
        self.assertNotIn("Делівері", body)
        self.assertNotIn("1499", html)
        for dash in DASHES:
            self.assertNotIn(dash, body)

    def test_delivery_page_without_free_shipping(self):
        s = ShopSettings.load()
        s.free_shipping_enabled = False
        s.save()
        body = _main(self.get(reverse("delivery")))
        self.assertNotIn("безкоштовна", body)
        self.assertIn("Доставку оплачуєте ви", body)

    def test_refund_page_matches_return_policy(self):
        html = self.get(reverse("refund"))
        body = _main(html)
        self.assertIn('id="merchant-return-policy"', body)
        self.assertIn("14 днів", body)
        self.assertIn("Новою Поштою", body)
        self.assertIn("Доставку назад", body)
        for dash in DASHES:
            self.assertNotIn(dash, body)

    def test_contacts_page(self):
        html = self.get("/contacts/")
        body = _main(html)
        self.assertIn('href="tel:+380963988875"', body)
        self.assertIn("+380 96 398 88 75", body)
        self.assertIn("mr.carpet.shop@gmail.com", body)
        self.assertIn("Ланівці", body)
        self.assertIn("вул. Незалежності 5а", body)
        self.assertIn("9:00-18:00", body)
        self.assertIn("https://www.google.com/maps/search/?api=1&amp;query=", body)
        self.assertIn("https://t.me/mrcarpet24", body)
        self.assertRegex(html, r'<link rel="canonical" href="https://mrcarpet24.com/contacts/"')
        robots = re.search(r'<meta name="robots"[^>]*>', html)
        self.assertNotIn("noindex", robots.group(0) if robots else "")
        for dash in DASHES:
            self.assertNotIn(dash, body)

    @override_settings(GOOGLE_PLACE_ID="ChIJtest")
    def test_contacts_map_uses_place_id(self):
        self.assertIn("query_place_id=ChIJtest", self.get("/contacts/"))

    def test_contacts_in_sitemap_and_footer(self):
        self.assertIn("/contacts/</loc>", self.get("/sitemap.xml"))
        footer = self.get("/").split("<footer", 1)[1]
        self.assertIn('href="/contacts/"', footer)

    def test_about_uses_site_facts(self):
        _product("kylym-about", 900)
        html = self.get(reverse("about"))
        self.assertNotIn("провідним постачальником", html)
        self.assertNotIn("кращими виробниками", html)
        self.assertIn("Ланівці", html)
        self.assertIn("1 модель", html)
        self.assertIn("Від 1777 грн доставка", html)
        main = html.split('<section class="banner', 1)[1].split("<footer", 1)[0]
        for dash in DASHES:
            self.assertNotIn(dash, main)

    def test_checkout_transit_matches_schema(self):
        html = self.client.get(reverse("checkout")).content.decode()
        self.assertIn('<div class="basket__checkbox-item-time">1-5 днів</div>', html)
        self.assertNotIn("Від 3 днів</div>\n                                    <div\n", html)


class PdpBuyBoxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product, cls.attr = _product("kylym-pdp", 2500)
        ProductAttribute.objects.create(
            product=cls.product, size=Size.objects.create(title="1.2x2.0"), price=1200, quantity=1
        )

    def test_trust_lines_and_size_in_cm(self):
        html = self.client.get(self.product.get_absolute_url()).content.decode()
        trust = html.split('<ul class="product__trust">', 1)[1].split("</ul>", 1)[0]
        self.assertIn("Доставка Новою Поштою по всій Україні, 1-5 днів", trust)
        self.assertIn("Оплата при отриманні", trust)
        self.assertIn("Повернення протягом 14 днів", trust)
        self.assertIn('href="tel:+380963988875"', trust)
        self.assertIn(f'href="{reverse("refund")}"', trust)
        # chips keep the stored label (JS / AR read it), the line shows cm
        self.assertRegex(html, r'class="size-label[^"]*"\s*>\s*2\.0х3\.0\s*<')
        self.assertIn(
            f'class="product__size-cm-value is-default" data-for="{self.attr.pk}">200x300 см<', html
        )
        self.assertIn(">120x200 см<", html)
        self.assertIn(f'.size-label.active[data-item="{self.attr.pk}"]', html)
