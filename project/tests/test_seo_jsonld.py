"""Unit tests for Product / Merchant / ProductGroup JSON-LD (Phase 7)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import RequestFactory, SimpleTestCase

from project.seo_jsonld import (
    ORG_NAME,
    merchant_return_policy,
    organization_graph,
    product_graph,
)


def _attr(price=1000, quantity=2, custom=False):
    attr = MagicMock()
    attr.custom_attribute = custom
    attr.custom_price = price if custom else None
    attr.quantity = quantity
    attr.get_total_price.return_value = price
    attr.size = None
    return attr


def _product(**kwargs):
    defaults = {
        "pk": 61,
        "title": "Килим тестовий синій",
        "meta_description": "Опис товару для SEO.",
        "description": "",
        "image": SimpleNamespace(url="/media/products/a.webp"),
        "active_color": SimpleNamespace(title="Синій"),
        "color_group": None,
        "get_absolute_url": lambda: "/product/test-blue/",
        "categories": MagicMock(),
        "reviews": MagicMock(),
        "product_attr": MagicMock(),
        "product_specs": MagicMock(),
    }
    defaults["categories"].first.return_value = None
    defaults["reviews"].all.return_value = []
    defaults["product_specs"].select_related.return_value.all.return_value = []
    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value = [_attr()]
    defaults["product_attr"] = qs
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class SeoJsonLdPhase7Tests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/product/test-blue/")
        self.request.META["HTTP_HOST"] = "testserver"

    def test_organization_has_return_policy(self):
        org = organization_graph(self.request)
        policy = org["hasMerchantReturnPolicy"]
        self.assertEqual(policy["merchantReturnDays"], 14)
        self.assertEqual(policy["applicableCountry"], "UA")
        self.assertIn("/refund/", policy["merchantReturnLink"])
        self.assertIn(
            "https://www.instagram.com/mr.carpet.shop/", org["sameAs"]
        )
        self.assertEqual(len(org["sameAs"]), 4)

    def test_single_product_merchant_fields(self):
        product = _product()
        data = product_graph(self.request, product)
        self.assertEqual(data["@type"], "Product")
        self.assertEqual(data["sku"], "61")
        self.assertEqual(data["brand"]["name"], ORG_NAME)
        self.assertEqual(data["color"], "Синій")
        offers = data["offers"]
        self.assertIn("priceValidUntil", offers)
        self.assertEqual(offers["shippingDetails"]["@type"], "OfferShippingDetails")
        self.assertEqual(
            offers["hasMerchantReturnPolicy"]["@type"], "MerchantReturnPolicy"
        )
        self.assertEqual(offers["hasMerchantReturnPolicy"]["merchantReturnDays"], 14)

    def test_color_group_emits_product_group(self):
        blue = _product(pk=61, title="Килим A синій")
        red = _product(
            pk=62,
            title="Килим A червоний",
            active_color=SimpleNamespace(title="Червоний"),
            get_absolute_url=lambda: "/product/test-red/",
            image=SimpleNamespace(url="/media/products/b.webp"),
        )
        group = SimpleNamespace(pk=7, name="Килим A")
        variants_qs = MagicMock()
        variants_qs.select_related.return_value.order_by.return_value = [blue, red]
        group.variants = variants_qs
        blue.color_group = group
        red.color_group = group

        data = product_graph(self.request, blue)
        self.assertIsInstance(data, list)
        pg = data[0]
        self.assertEqual(pg["@type"], "ProductGroup")
        self.assertEqual(pg["productGroupID"], "cg-7")
        self.assertEqual(pg["variesBy"], ["https://schema.org/color"])
        self.assertEqual(len(pg["hasVariant"]), 2)
        current = pg["hasVariant"][0]
        stub = pg["hasVariant"][1]
        self.assertEqual(current["sku"], "61")
        self.assertEqual(current["inProductGroupWithID"], "cg-7")
        self.assertIn("offers", current)
        self.assertEqual(stub["sku"], "62")
        self.assertNotIn("offers", stub)
        self.assertEqual(stub["color"], "Червоний")

    def test_merchant_return_policy_id_stable(self):
        policy = merchant_return_policy(self.request)
        self.assertTrue(policy["@id"].endswith("/refund/#merchant-return-policy"))
