"""Unit tests for Product / Merchant / ProductGroup JSON-LD (Phase 7)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from project.seo_jsonld import (
    ORG_NAME,
    merchant_return_policy,
    organization_graph,
    product_graph,
)

_ATTR_PK = iter(range(500, 10_000))


def _attr(price=1000, quantity=2, custom=False, size=None, pk=None):
    attr = MagicMock()
    attr.pk = pk if pk is not None else next(_ATTR_PK)
    attr.custom_attribute = custom
    attr.custom_price = price if custom else None
    attr.quantity = quantity
    attr.get_total_price.return_value = price
    attr.size = SimpleNamespace(title=size) if size else None
    return attr


def _product(attrs=None, **kwargs):
    defaults = {
        "pk": 61,
        "title": "Килим тестовий синій",
        "meta_description": "Опис товару для SEO.",
        "description": "",
        "image": SimpleNamespace(url="/media/products/a.webp", name="products/a.webp"),
        "active_color": SimpleNamespace(title="Синій"),
        "color_group": None,
        "get_absolute_url": lambda: "/catalog/product/test-blue/",
        "categories": MagicMock(),
        "reviews": MagicMock(),
        "product_attr": MagicMock(),
        "product_specs": MagicMock(),
    }
    defaults["categories"].all.return_value = []
    defaults["product_specs"].select_related.return_value.all.return_value = []
    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value = (
        attrs if attrs is not None else [_attr(pk=301)]
    )
    defaults["product_attr"] = qs
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _walk(node):
    """Every dict in a JSON-LD tree."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _color_pair(blue_attrs=None, red_attrs=None):
    blue = _product(pk=61, title="Килим A синій", attrs=blue_attrs)
    red = _product(
        pk=62,
        title="Килим A червоний",
        attrs=red_attrs,
        active_color=SimpleNamespace(title="Червоний"),
        get_absolute_url=lambda: "/catalog/product/test-red/",
        image=SimpleNamespace(url="/media/products/b.webp", name="products/b.webp"),
    )
    group = SimpleNamespace(pk=7, name="Килим A")
    variants_qs = MagicMock()
    variants_qs.select_related.return_value.order_by.return_value = [blue, red]
    group.variants = variants_qs
    blue.color_group = group
    red.color_group = group
    return blue, red


class SeoJsonLdPhase7Tests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/catalog/product/test-blue/")
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
        # Same id as the Merchant feed item (<product.pk>-<attr.pk>).
        self.assertEqual(data["sku"], "61-301")
        self.assertEqual(data["brand"]["name"], ORG_NAME)
        self.assertEqual(data["color"], "Синій")
        offers = data["offers"]
        self.assertEqual(offers["@type"], "Offer")
        self.assertIn("priceValidUntil", offers)
        self.assertEqual(offers["shippingDetails"]["@type"], "OfferShippingDetails")
        self.assertEqual(
            offers["hasMerchantReturnPolicy"]["@type"], "MerchantReturnPolicy"
        )
        self.assertEqual(offers["hasMerchantReturnPolicy"]["merchantReturnDays"], 14)

    def test_single_size_plus_custom_size_is_one_offer(self):
        """A per-m² custom size next to one real size used to make a fake
        AggregateOffer range (price per m² is not a price)."""
        product = _product(attrs=[_attr(price=900, pk=11), _attr(price=450, custom=True)])
        data = product_graph(self.request, product)
        self.assertEqual(data["@type"], "Product")
        self.assertEqual(data["offers"]["@type"], "Offer")
        self.assertEqual(data["offers"]["price"], 900)

    def test_custom_size_only_keeps_product(self):
        product = _product(attrs=[_attr(price=450, custom=True)])
        data = product_graph(self.request, product)
        self.assertEqual(data["@type"], "Product")
        self.assertEqual(data["offers"]["price"], 450)

    def test_multi_size_is_product_group_with_offer_per_size(self):
        product = _product(
            attrs=[
                _attr(price=450, size="0.6x1.0", pk=11),
                _attr(price=900, size="0.8x1.5", pk=12, quantity=0),
            ]
        )
        data = product_graph(self.request, product)
        self.assertEqual(data["@type"], "ProductGroup")
        self.assertEqual(data["productGroupID"], "61")
        self.assertEqual(data["variesBy"], ["https://schema.org/size"])
        self.assertTrue(data["url"].endswith("/catalog/product/test-blue/"))
        self.assertEqual(data["brand"]["name"], ORG_NAME)
        self.assertIn("description", data)
        small, large = data["hasVariant"]
        self.assertEqual(small["sku"], "61-11")
        self.assertEqual(small["size"], "60x100 см")
        self.assertEqual(small["inProductGroupWithID"], "61")
        self.assertEqual(small["offers"]["@type"], "Offer")
        self.assertEqual(small["offers"]["price"], 450)
        self.assertTrue(small["offers"]["url"].endswith("/catalog/product/test-blue/?size=11"))
        self.assertEqual(large["offers"]["availability"], "https://schema.org/OutOfStock")
        self.assertIn("image", small)
        # Merchant listings refuse AggregateOffer: none anywhere.
        types = {n.get("@type") for n in _walk(data)}
        self.assertNotIn("AggregateOffer", types)

    def test_color_group_emits_product_group(self):
        blue, _red = _color_pair()
        data = product_graph(self.request, blue)
        self.assertEqual(data["@type"], "ProductGroup")
        self.assertEqual(data["productGroupID"], "cg-7")
        self.assertEqual(data["variesBy"], ["https://schema.org/color"])
        # Multi-page group: no canonical url of its own.
        self.assertNotIn("url", data)
        self.assertNotIn("@id", data)
        self.assertEqual(len(data["hasVariant"]), 2)
        current, other = data["hasVariant"]
        self.assertEqual(current["sku"], "61-301")
        self.assertEqual(current["inProductGroupWithID"], "cg-7")
        self.assertEqual(current["color"], "Синій")
        self.assertEqual(current["offers"]["@type"], "Offer")
        # Other colour page: url-only reference, never an offer-less Product
        # (those were invalid Product snippet items).
        self.assertEqual(set(other), {"url"})
        self.assertTrue(other["url"].endswith("/catalog/product/test-red/"))

    def test_color_group_with_sizes_varies_by_both(self):
        blue, _red = _color_pair(
            blue_attrs=[_attr(price=450, size="0.6x1.0"), _attr(price=900, size="0.8x1.5")]
        )
        data = product_graph(self.request, blue)
        self.assertEqual(
            data["variesBy"],
            ["https://schema.org/size", "https://schema.org/color"],
        )
        offers = [v for v in data["hasVariant"] if "offers" in v]
        self.assertEqual(len(offers), 2)
        self.assertEqual(len([v for v in data["hasVariant"] if set(v) == {"url"}]), 1)

    def test_selected_size_emits_single_offer_for_that_size(self):
        """`?size=<attr.pk>` is the Merchant feed link: one Offer, that price."""
        chosen = _attr(price=900, size="0.8x1.5", pk=12)
        product = _product(attrs=[_attr(price=450, size="0.6x1.0", pk=11), chosen])
        data = product_graph(self.request, product, selected_attr=chosen)
        self.assertEqual(data["@type"], "Product")
        self.assertEqual(data["sku"], "61-12")
        self.assertEqual(data["size"], "80x150 см")
        self.assertEqual(data["offers"]["@type"], "Offer")
        self.assertEqual(data["offers"]["price"], 900)
        self.assertTrue(data["offers"]["url"].endswith("/catalog/product/test-blue/?size=12"))
        self.assertTrue(data["url"].endswith("/catalog/product/test-blue/"))

    def test_selected_size_of_other_product_is_ignored(self):
        product = _product(attrs=[_attr(price=450, pk=11), _attr(price=900, pk=12)])
        stranger = _attr(price=1, pk=99)
        data = product_graph(self.request, product, selected_attr=stranger)
        self.assertEqual(data["@type"], "ProductGroup")

    def test_placeholder_image_is_not_offered(self):
        product = _product(
            image=SimpleNamespace(url="/media/products/default.png", name="products/default.png")
        )
        data = product_graph(self.request, product)
        self.assertNotIn("image", data)

    def test_merchant_return_policy_id_stable(self):
        policy = merchant_return_policy(self.request)
        self.assertTrue(policy["@id"].endswith("/refund/#merchant-return-policy"))


class OfferShippingRateTests(SimpleTestCase):
    def _settings(self, **kw):
        from types import SimpleNamespace as NS
        base = dict(free_shipping_enabled=True, free_shipping_threshold=1499, delivery_from_price=90)
        base.update(kw)
        return NS(**base)

    def test_below_threshold_charges_from_price(self):
        from unittest import mock
        from project.seo_jsonld import offer_shipping_details
        with mock.patch("project.free_shipping.get_shop_settings", return_value=self._settings()):
            self.assertEqual(offer_shipping_details(400)["shippingRate"]["value"], "90")
            self.assertEqual(offer_shipping_details(1499)["shippingRate"]["value"], "0")
            self.assertEqual(offer_shipping_details(5500)["shippingRate"]["value"], "0")


class ModelKeyTests(SimpleTestCase):
    def test_shape_twins_share_a_key(self):
        from catalog.services.product_variants import model_key

        pairs = [
            ("Килим овальний сірий Mira 24031.619 O", "Килим прямокутний сірий Mira 24031.619"),
            ("Килим Mira 24058/160 Овал", "Килим Mira 24058/160"),
            ("Килим овальний бежевий La Rosa GK500", "Килим прямокутний бежевий La Rosa GK500"),
            ("Килим овальним світло-бежевий Fashion 32007.110 O", "Килим прямокутний світло-бежевий Fashion 32007.110"),
        ]
        for oval, rect in pairs:
            self.assertEqual(model_key(oval), model_key(rect), (oval, rect))
            self.assertTrue(model_key(oval))

    def test_different_codes_differ(self):
        from catalog.services.product_variants import model_key

        self.assertNotEqual(
            model_key("Килим овальний 1918/19"), model_key("Килим прямокутний 1918/91")
        )
        self.assertEqual(model_key("Килим овальний оранжевий"), "")

    def test_shape_label_prefers_title_over_wrong_spec(self):
        from catalog.services.product_variants import shape_label

        row = SimpleNamespace(
            specification=SimpleNamespace(title="Форма килима"),
            spec_value=SimpleNamespace(title="Прямокутник"),
        )
        specs = MagicMock()
        specs.all.return_value = [row]
        oval = SimpleNamespace(title="Килим овальний бежевий La Rosa GK500", product_specs=specs)
        self.assertEqual(shape_label(oval), "Овальний")
        door = SimpleNamespace(title="Килим Під двері зелений", product_specs=specs)
        self.assertEqual(shape_label(door), "Прямокутний")


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL="https://mrcarpet24.com")
class ProductVariantsPageTests(TestCase):
    """Rendered PDP: sibling links block + JSON-LD shape."""

    @classmethod
    def setUpTestData(cls):
        from catalog.models import ColorGroup, Product, ProductAttribute, ProductColor, Size

        small = Size.objects.create(title="0.6x1.0")
        large = Size.objects.create(title="0.8x1.5")
        grey = ProductColor.objects.create(title="сірий", slug="sirii-t", color="#888888")
        beige = ProductColor.objects.create(title="бежевий", slug="bezhevii-t", color="#d8c8a8")

        def make(title, slug, color=None, sizes=((small, 450),), group=None):
            p = Product.objects.create(title=title, slug=slug, active_color=color, color_group=group)
            for size, price in sizes:
                ProductAttribute.objects.create(product=p, size=size, price=price, quantity=3)
            return p

        cls.oval = make(
            "Килим овальний сірий Mira 24031.619 O",
            "kilim-ovalnii-sirii-mira-24031619-o",
            grey,
            sizes=((small, 450), (large, 900)),
        )
        cls.rect = make(
            "Килим прямокутний сірий Mira 24031.619",
            "kilim-priamokutnii-sirii-mira-24031619",
            grey,
        )
        group = ColorGroup.objects.create(name="Килим овальний Mira 24031")
        cls.oval.color_group = group
        cls.oval.save(update_fields=["color_group"])
        cls.oval_beige = make(
            "Килим овальний бежевий Mira 24031.243 O",
            "kilim-ovalnii-bezhevii-mira-24031243-o",
            beige,
            group=group,
        )
        cls.unrelated = make("Килим овальний оранжевий", "kilim-ovalnii-oranzhevii")

    def _jsonld(self, html):
        import re

        out = []
        for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            data = json.loads(raw)
            for node in data if isinstance(data, list) else [data]:
                if node.get("@type") in ("Product", "ProductGroup"):
                    out.append(node)
        return out

    def test_block_links_shape_and_colour_siblings(self):
        html = self.client.get(self.oval.get_absolute_url()).content.decode()
        self.assertIn("Інші форми та кольори цієї моделі", html)
        self.assertIn("Цей килим овальної форми.", html)
        self.assertIn("Така ж модель є й іншої форми.", html)
        self.assertIn(f'href="{self.rect.get_absolute_url()}"', html)
        self.assertIn(f'href="{self.oval_beige.get_absolute_url()}"', html)
        self.assertNotIn(f'href="{self.unrelated.get_absolute_url()}"', html)
        self.assertNotIn("—", html.split("product-variants-links")[1].split("</section>")[0])

    def test_rectangular_twin_links_back_to_oval(self):
        html = self.client.get(self.rect.get_absolute_url()).content.decode()
        self.assertIn(f'href="{self.oval.get_absolute_url()}"', html)
        self.assertIn("Овальний, сірий", html)

    def test_no_block_without_siblings(self):
        html = self.client.get(self.unrelated.get_absolute_url()).content.decode()
        self.assertNotIn("product-variants-links__list", html)

    def test_pdp_jsonld_group_and_size_param(self):
        html = self.client.get(self.oval.get_absolute_url()).content.decode()
        (group,) = self._jsonld(html)
        self.assertEqual(group["@type"], "ProductGroup")
        self.assertEqual(
            group["variesBy"], ["https://schema.org/size", "https://schema.org/color"]
        )
        priced = [v for v in group["hasVariant"] if "offers" in v]
        self.assertEqual(len(priced), 2)
        self.assertEqual(
            [v["url"] for v in group["hasVariant"] if set(v) == {"url"}],
            [f"https://mrcarpet24.com{self.oval_beige.get_absolute_url()}"],
        )

        attr = self.oval.product_attr.get(price=900)
        html = self.client.get(f"{self.oval.get_absolute_url()}?size={attr.pk}").content.decode()
        (node,) = self._jsonld(html)
        self.assertEqual(node["@type"], "Product")
        self.assertEqual(node["offers"]["price"], 900)
        self.assertTrue(node["offers"]["url"].endswith(f"?size={attr.pk}"))
