"""Google Merchant feed."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest import TestCase as PlainTestCase

from django.test import TestCase

from project.merchant_feed import (
    build_items,
    description_with_facts,
    feed_product_type,
    price_band,
    size_class,
    feed_products,
    feed_title,
    format_size,
    is_color_word,
    parse_title,
    product_color,
    product_description,
    render_feed,
    size_dimensions,
)

G = "{http://base.google.com/ns/1.0}"


class AdsLabelTests(PlainTestCase):
    def test_product_type_hierarchy(self):
        cats = [SimpleNamespace(title="Для ванни"), SimpleNamespace(title="Турецькі")]
        self.assertEqual(feed_product_type(cats), "Килими > Турецькі > Для ванни")
        self.assertEqual(feed_product_type([SimpleNamespace(title="Українські")]), "Килими > Українські")
        self.assertEqual(feed_product_type([]), "")

    def test_price_band(self):
        self.assertEqual(price_band(450), "до 500 грн")
        self.assertEqual(price_band(500), "500-999 грн")
        self.assertEqual(price_band("1999.00"), "1000-2499 грн")
        self.assertEqual(price_band(2500), "від 2500 грн")

    def test_size_class(self):
        self.assertEqual(size_class((60, 100)), "малий")
        self.assertEqual(size_class((160, 230)), "середній")
        self.assertEqual(size_class((200, 300)), "великий")
        self.assertEqual(size_class(None), "")

    def test_description_facts_line(self):
        text = description_with_facts("Гарний килим.", "60x100 см", "сірий/білий", "Поліпропілен")
        self.assertEqual(text, "Гарний килим.\n\nРозмір: 60x100 см. Колір: сірий, білий. Матеріал: поліпропілен.")
        self.assertEqual(description_with_facts("Опис", "", "", ""), "Опис")
        long = description_with_facts("я" * 6000, "60x100 см", "", "")
        self.assertLessEqual(len(long), 5000)
        self.assertTrue(long.endswith("Розмір: 60x100 см."))


class FormatSizeTests(PlainTestCase):
    def test_metres_cyrillic(self):
        self.assertEqual(format_size("1.2х2.0"), "120x200 см")
        self.assertEqual(format_size("0.67х1.2"), "67x120 см")
        self.assertEqual(format_size("1.5x2.3"), "150x230 см")

    def test_passthrough(self):
        self.assertEqual(format_size("∅ 67 см"), "∅ 67 см")
        self.assertEqual(format_size(""), "")


class RenderFeedTests(PlainTestCase):
    def test_valid_xml_and_escaping(self):
        xml = render_feed([{
            "id": "1-2", "title": "Килим <A&B>", "price": "400.00 UAH",
            "sale_price": "", "additional_image_link": ["https://x/1.jpg", "https://x/2.jpg"],
        }])
        root = ET.fromstring(xml.encode("utf-8"))
        item = root.find("channel/item")
        self.assertEqual(item.find(f"{G}title").text, "Килим <A&B>")
        self.assertIsNone(item.find(f"{G}sale_price"))
        self.assertEqual(len(item.findall(f"{G}additional_image_link")), 2)

    def test_nested_and_empty_values(self):
        xml = render_feed([{
            "id": "1-2",
            "product_detail": [
                {"section_name": "S", "attribute_name": "A&B", "attribute_value": "<v>"},
                {"section_name": "", "attribute_name": "", "attribute_value": ""},
            ],
            "product_highlight": [],
            "pattern": "",
        }])
        item = ET.fromstring(xml.encode("utf-8")).find("channel/item")
        details = item.findall(f"{G}product_detail")
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].findtext(f"{G}attribute_name"), "A&B")
        self.assertEqual(details[0].findtext(f"{G}attribute_value"), "<v>")
        self.assertIsNone(item.find(f"{G}pattern"))


class FeedViewTests(TestCase):
    def test_endpoint(self):
        resp = self.client.get("/feeds/google-merchant.xml", secure=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/xml", resp["Content-Type"])
        ET.fromstring(resp.content)


def _p(title, **kw):
    return SimpleNamespace(title=title, active_color=None, **kw)


class TitleParsingTests(PlainTestCase):
    def test_bath_mat_model_capitalized_color_after_model(self):
        self.assertEqual(
            feed_title(_p("Килим фіолетово-ліловий для ванни isadora"), "60x100 см"),
            "Килим для ванни Isadora фіолетово-ліловий 60x100 см",
        )

    def test_shape_model_color_size(self):
        self.assertEqual(
            feed_title(_p("Килим овальний темно-сірий La rosa GK503"), "120x200 см"),
            "Килим овальний La Rosa GK503 темно-сірий 120x200 см",
        )

    def test_shape_from_spec_when_title_has_none(self):
        specs = [("Форма килима", "Прямокутник")]
        self.assertEqual(
            feed_title(_p("Килим Mira 24058/160"), "60x110 см", specs),
            "Килим прямокутний Mira 24058/160 60x110 см",
        )

    def test_shape_noun_and_typo_normalized(self):
        self.assertEqual(
            feed_title(_p("Килим Mira 24058/160 Овал"), "60x110 см"),
            "Килим овальний Mira 24058/160 60x110 см",
        )
        self.assertEqual(
            feed_title(_p("Килим овальним світло-бежевий Fashion 32007.110 O"), "60x110 см"),
            "Килим овальний Fashion 32007.110 O світло-бежевий 60x110 см",
        )

    def test_split_compound_color_and_placeholder_dropped(self):
        self.assertEqual(
            feed_title(_p("Килим фіолетово білий wilma"), "60x100 см"),
            "Килим Wilma фіолетово-білий 60x100 см",
        )
        self.assertEqual(
            feed_title(_p("Килим прямокутний сірий без назви"), "80x150 см"),
            "Килим прямокутний сірий 80x150 см",
        )

    def test_door_mat_and_theme_words(self):
        self.assertEqual(
            feed_title(_p("Килим Під двері коричневий"), "40x60 см"),
            "Килим під двері коричневий 40x60 см",
        )
        self.assertEqual(
            feed_title(_p("Килим прямокутний зелений місто"), "80x150 см"),
            "Килим прямокутний місто зелений 80x150 см",
        )

    def test_unknown_structure_passes_through(self):
        self.assertEqual(feed_title(_p("Shaggy  grey"), "50x80 см"), "Shaggy grey 50x80 см")

    def test_title_limit(self):
        self.assertLessEqual(len(feed_title(_p("Килим " + "Abc " * 60), "50x80 см")), 150)

    def test_color_words(self):
        for w in ("сірий", "темно-сірий", "графіт", "сіро-коричневий", "бежево-сірий"):
            self.assertTrue(is_color_word(w), w)
        for w in ("овальний", "Grey", "ванни", "Mira", "місто", "фіолетово"):
            self.assertFalse(is_color_word(w), w)

    def test_color_sources(self):
        self.assertEqual(product_color(_p("Килим прямокутний сірий Flex"), []), "сірий")
        prod = _p("Килим Flex")
        prod.active_color = SimpleNamespace(title="Синій")
        self.assertEqual(product_color(prod, []), "Синій")
        self.assertEqual(product_color(_p("Килим Flex"), [("Колір", "Бежевий")]), "Бежевий")
        self.assertEqual(product_color(_p("Килим Flex"), []), "")
        self.assertEqual(parse_title("Килим Flex")["colors"], [])


class DimensionsDescriptionTests(PlainTestCase):
    def test_dimensions(self):
        self.assertEqual(size_dimensions("120x200 см"), (120, 200))
        self.assertEqual(size_dimensions("∅ 67 см"), (67, 67))
        self.assertIsNone(size_dimensions("Великий"))

    def test_description_prefers_longer_full_text(self):
        full = "<p>Перший&nbsp;абзац.</p>\n" + "Довгий опис. " * 30
        prod = SimpleNamespace(title="T", description=full, meta_description="Коротко.")
        text = product_description(prod)
        self.assertTrue(text.startswith("Перший абзац."))
        self.assertNotIn("<p>", text)

    def test_description_fallbacks_and_limit(self):
        prod = SimpleNamespace(title="T", description="Коротко", meta_description="Мета опис довший")
        self.assertEqual(product_description(prod), "Мета опис довший")
        prod = SimpleNamespace(title="T", description=None, meta_description="")
        self.assertEqual(product_description(prod), "T")
        prod = SimpleNamespace(title="T", description="я" * 6000, meta_description="")
        self.assertEqual(len(product_description(prod)), 5000)


def _make_product(cls):
    from catalog.models import (
        Product,
        ProductAttribute,
        ProductSpecification,
        Size,
        Specification,
        SpecificationValue,
    )

    cls.product = Product.objects.create(
        title="Килим фіолетово-ліловий для ванни isadora",
        slug="kylym-isadora",
        image="products/isadora.webp",
        meta_description="Коротко.",
        description="Мʼякий килимок для ванної, вбирає воду, не ковзає. " * 3,
    )
    cls.small = ProductAttribute.objects.create(
        product=cls.product, size=Size.objects.create(title="0.6х1.0"),
        price=600, quantity=3, sort_order=1,
    )
    cls.big = ProductAttribute.objects.create(
        product=cls.product, size=Size.objects.create(title="0.8х1.5"),
        price=1000, discount=10, quantity=0, sort_order=2,
    )
    ProductAttribute.objects.create(
        product=cls.product, custom_attribute=True, custom_price=500,
        min_len=1, max_len=3, quantity=1, sort_order=3,
    )
    for name, value in (
        ("Склад килима", "Поліпропілен"),
        ("Форма килима", "Прямокутник"),
        ("Висота ворса", "6.5 мм"),
        ("Малюнок", "Однотонний"),
    ):
        spec = Specification.objects.create(title=name)
        ProductSpecification.objects.create(
            product=cls.product, specification=spec,
            spec_value=SpecificationValue.objects.create(title=value, specification=spec),
        )


class BuildItemsDbTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _make_product(cls)

    def _items(self):
        return build_items(feed_products())

    def test_one_item_per_fixed_size_with_variant_link(self):
        items = self._items()
        self.assertEqual([i["id"] for i in items], [
            f"{self.product.pk}-{self.small.pk}", f"{self.product.pk}-{self.big.pk}",
        ])
        self.assertTrue(items[0]["link"].endswith(
            f"/catalog/product/kylym-isadora/?size={self.small.pk}"
        ))
        self.assertTrue(items[1]["link"].endswith(f"?size={self.big.pk}"))

    def test_attributes_from_db(self):
        small, big = self._items()
        self.assertEqual(
            small["title"], "Килим прямокутний для ванни Isadora фіолетово-ліловий 60x100 см"
        )
        self.assertEqual(small["color"], "фіолетово-ліловий")
        self.assertEqual(small["material"], "Поліпропілен")
        self.assertEqual(small["pattern"], "Однотонний")
        self.assertEqual((small["product_width"], small["product_length"]), ("60 cm", "100 cm"))
        self.assertTrue(small["description"].startswith("Мʼякий килимок"))
        self.assertEqual(
            [(d["attribute_name"], d["attribute_value"]) for d in small["product_detail"]],
            [("Склад килима", "Поліпропілен"), ("Форма килима", "Прямокутник"),
             ("Висота ворса", "6.5 мм"), ("Малюнок", "Однотонний")],
        )
        self.assertEqual(len(small["product_highlight"]), 4)
        self.assertNotIn("mpn", small)
        self.assertEqual(small["brand"], "mr.Carpet")
        self.assertEqual(big["sale_price"], "900.00 UAH")
        self.assertEqual(big["availability"], "out_of_stock")

    def test_rendered_xml_nested_product_detail(self):
        root = ET.fromstring(render_feed(self._items()).encode("utf-8"))
        item = root.find("channel/item")
        details = item.findall(f"{G}product_detail")
        self.assertEqual(len(details), 4)
        self.assertEqual(details[0].findtext(f"{G}section_name"), "Характеристики")
        self.assertEqual(details[0].findtext(f"{G}attribute_value"), "Поліпропілен")
        self.assertEqual(item.findtext(f"{G}material"), "Поліпропілен")

    def test_shape_detail_only_from_real_data(self):
        from catalog.models import ProductSpecification

        ProductSpecification.objects.filter(specification__title="Форма килима").delete()
        names = [d["attribute_name"] for d in self._items()[0]["product_detail"]]
        self.assertNotIn("Форма", names)  # no shape word anywhere -> nothing invented
        self.product.title = "Килим овальний Isadora"
        self.product.save()
        rows = [(d["attribute_name"], d["attribute_value"]) for d in self._items()[0]["product_detail"]]
        self.assertIn(("Форма", "Овал"), rows)


class PromFeedSharedHelpersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _make_product(cls)

    def test_offers_use_specs_and_full_description(self):
        from project.prom_feed import build_feed

        root = ET.fromstring(build_feed().encode("utf-8"))
        offers = root.findall("shop/offers/offer")
        self.assertEqual(len(offers), 2)
        params = {p.get("name"): p.text for p in offers[0].findall("param")}
        self.assertEqual(params["Розмір"], "60x100 см")
        self.assertEqual(params["Колір"], "фіолетово-ліловий")
        self.assertEqual(params["Склад килима"], "Поліпропілен")
        self.assertTrue(offers[0].findtext("description").startswith("Мʼякий килимок"))


class PdpSizePreselectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _make_product(cls)

    @staticmethod
    def _active_size(html):
        for m in re.finditer(r'<div\s+data-item="(\d+)".*?class="([^"]*)"', html, re.S):
            if "size-label" in m.group(2) and "active" in m.group(2).split():
                return int(m.group(1))
        return None

    def _get(self, query=""):
        resp = self.client.get(f"/catalog/product/kylym-isadora/{query}", secure=True)
        self.assertEqual(resp.status_code, 200, query)
        return resp.content.decode()

    def test_size_param_preselects_size_and_price(self):
        html = self._get(f"?size={self.big.pk}")
        self.assertEqual(self._active_size(html), self.big.pk)
        self.assertIn('<span class="cart_item_price-value">900</span>', html)
        self.assertIn('<span class="cart_item_old_price-value">1000</span>', html)
        self.assertIn(f'data-product-id="{self.big.pk}"', html)
        canonical = re.search(r'rel="canonical"\s+href="([^"]+)"', html)
        self.assertIsNotNone(canonical)
        self.assertNotIn("?", canonical.group(1))

    def test_default_and_invalid_size_fall_back(self):
        for query in ("", "?size=999999", "?size=abc"):
            html = self._get(query)
            self.assertEqual(self._active_size(html), self.small.pk, query)
            self.assertIn('<span class="cart_item_price-value">600</span>', html)

    def test_custom_size_attr_is_not_preselectable(self):
        custom = self.product.product_attr.get(custom_attribute=True)
        html = self._get(f"?size={custom.pk}")
        self.assertEqual(self._active_size(html), self.small.pk)
