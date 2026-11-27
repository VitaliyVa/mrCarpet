"""Rozetka Marketplace YML feed (/feeds/rozetka.xml)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from unittest import TestCase as PlainTestCase

from django.test import SimpleTestCase, TestCase, override_settings

from catalog.models import (
    Product,
    ProductAttribute,
    ProductCategory,
    ProductImage,
    ProductSpecification,
    Size,
    Specification,
    SpecificationValue,
)
from project.prom_feed import (
    ROZETKA_FALLBACK_CATEGORY_ID,
    ROZETKA_FALLBACK_VENDOR,
    build_rozetka_feed,
    render_rozetka_feed,
    rozetka_picture_url,
    rozetka_price,
    rozetka_vendor,
)
from project.tests.test_merchant_feed import _make_product

ID_RE = re.compile(r"^[A-Za-z0-9]+$")


def _spec(product, name, value):
    spec = Specification.objects.create(title=name)
    ProductSpecification.objects.create(
        product=product,
        specification=spec,
        spec_value=SpecificationValue.objects.create(title=value, specification=spec),
    )


class RozetkaHelpersTests(PlainTestCase):
    def test_price_markup_math(self):
        self.assertEqual(rozetka_price(600, Decimal("1.25")), 750)
        self.assertEqual(rozetka_price(900, Decimal("1.25")), 1125)
        self.assertEqual(rozetka_price(333, Decimal("1.25")), 416)  # 416.25
        self.assertEqual(rozetka_price(10, Decimal("1.25")), 13)  # 12.5 rounds up
        self.assertEqual(rozetka_price(449.5, Decimal("1.25")), 562)  # float site price

    def test_vendor_from_brand_spec_else_fallback(self):
        self.assertEqual(rozetka_vendor([("Бренд", "Dinarsu")]), ("Dinarsu", False))
        self.assertEqual(rozetka_vendor([("Торгова марка", "Vals")]), ("Vals", False))
        self.assertEqual(
            rozetka_vendor([("Склад килима", "Поліпропілен")]),
            (ROZETKA_FALLBACK_VENDOR, True),
        )
        self.assertEqual(rozetka_vendor([]), ("Без бренду", True))
        self.assertEqual(rozetka_vendor([], "Килим прямокутний Mira 24192/261"), ("Karat", False))
        self.assertEqual(rozetka_vendor([], "Килим Flex 19197-91"), ("Karat", False))
        self.assertEqual(rozetka_vendor([], "Килим La Rosa GK503"), ("Без бренду", True))

    def test_picture_url_percent_encoded(self):
        url = rozetka_picture_url("https://mrcarpet24.com/media/products/килим 1.jpg")
        self.assertTrue(url.isascii())
        self.assertNotIn(" ", url)
        self.assertEqual(
            rozetka_picture_url("https://mrcarpet24.com/media/a%20b.jpg"),
            "https://mrcarpet24.com/media/a%20b.jpg",
        )

    def test_render_escapes_and_cdata(self):
        xml = render_rozetka_feed(
            [{"id": 5, "name": "A & B"}],
            [{
                "id": "1x2", "group_id": "1", "available": "true", "stock_quantity": 2,
                "url": "https://mrcarpet24.com/catalog/product/x/?size=2",
                "price": 750, "currencyId": "UAH", "categoryId": 5,
                "pictures": ["https://mrcarpet24.com/media/a.jpg"],
                "vendor": "mr.Carpet", "article": "1x2",
                "name": 'Килим <A&B> "q"', "name_ua": 'Килим <A&B> "q"',
                "description": "Перший абзац ]]> тут.\n\nДругий & абзац.",
                "params": [('Назва "x"', "a<b")],
            }],
        )
        root = ET.fromstring(xml.encode("utf-8"))
        offer = root.find("shop/offers/offer")
        self.assertEqual(offer.findtext("name"), 'Килим <A&B> "q"')
        self.assertEqual(offer.find("param").get("name"), 'Назва "x"')
        self.assertEqual(offer.find("param").text, "a<b")
        desc = offer.findtext("description")
        self.assertIn("<p>Перший абзац ]]&gt; тут.</p>", desc)
        self.assertIn("<p>Другий &amp; абзац.</p>", desc)
        self.assertIn("<![CDATA[", xml)


@override_settings(SITE_URL="https://mrcarpet24.com", ROZETKA_PRICE_MARKUP="1.25")
class RozetkaFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _make_product(cls)
        cls.category = ProductCategory.objects.create(title="Для ванни", slug="dlya-vanni")
        cls.country = ProductCategory.objects.create(title="Турецькі", slug="turetski")
        cls.product.categories.add(cls.country, cls.category)
        ProductImage.objects.create(product=cls.product, image="products/gallery 1.jpg")

    def _root(self):
        return ET.fromstring(build_rozetka_feed().encode("utf-8"))

    def test_shop_structure(self):
        root = self._root()
        self.assertEqual(root.tag, "yml_catalog")
        self.assertRegex(root.get("date"), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        shop = root.find("shop")
        self.assertEqual(shop.findtext("name"), "Mr Carpet")
        self.assertEqual(shop.findtext("company"), "ФОП Стецюк Микола Олексійович")
        self.assertEqual(shop.findtext("url"), "https://mrcarpet24.com/")
        currency = shop.find("currencies/currency")
        self.assertEqual((currency.get("id"), currency.get("rate")), ("UAH", "1"))
        ids = {c.get("id") for c in shop.findall("categories/category")}
        self.assertIn(str(self.category.pk), ids)

    def test_offers_skip_custom_and_priceless(self):
        offers = self._root().findall("shop/offers/offer")
        self.assertEqual(len(offers), 2)  # custom-size attr skipped

    def test_ids_pattern_and_stability(self):
        offers = self._root().findall("shop/offers/offer")
        ids = [o.get("id") for o in offers]
        for offer_id in ids:
            self.assertRegex(offer_id, ID_RE)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(ids[0], f"{self.product.pk}x{self.small.pk}")
        self.assertEqual(offers[0].findtext("article"), ids[0])
        self.assertEqual(offers[0].get("group_id"), str(self.product.pk))

    def test_names_unique_and_limited(self):
        offers = self._root().findall("shop/offers/offer")
        names = [o.findtext("name") for o in offers]
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(names[0], "Килим прямокутний для ванни Isadora фіолетово-ліловий 60x100 см")
        for o in offers:
            self.assertEqual(o.findtext("name"), o.findtext("name_ua"))
            self.assertLessEqual(len(o.findtext("name")), 255)

    def test_duplicate_names_get_article_suffix(self):
        twin = Product.objects.create(
            title=self.product.title, slug="kylym-isadora-2", image="products/isadora2.webp",
            description="Опис двійника.",
        )
        _spec(twin, "Форма килима", "Прямокутник")
        ProductAttribute.objects.create(
            product=twin, size=Size.objects.get(title="0.6х1.0"), price=600, quantity=1,
        )
        offers = self._root().findall("shop/offers/offer")
        names = [o.findtext("name") for o in offers]
        self.assertEqual(len(names), 3)
        self.assertEqual(len(set(names)), 3)
        self.assertTrue(any(f"(арт. {twin.pk})" in n for n in names))

    def test_markup_math_and_discount(self):
        offers = {o.get("id"): o for o in self._root().findall("shop/offers/offer")}
        small = offers[f"{self.product.pk}x{self.small.pk}"]
        big = offers[f"{self.product.pk}x{self.big.pk}"]
        self.assertEqual(small.findtext("price"), str(round(600 * 1.25)))  # 750
        # 1000 UAH with 10% discount = 900 on the site -> 900 * 1.25
        self.assertEqual(big.findtext("price"), "1125")
        self.assertEqual(small.findtext("currencyId"), "UAH")

    @override_settings(ROZETKA_PRICE_MARKUP="1.1")
    def test_markup_comes_from_settings(self):
        offers = self._root().findall("shop/offers/offer")
        self.assertEqual(offers[0].findtext("price"), "660")

    def test_stock_quantity_and_available(self):
        offers = self._root().findall("shop/offers/offer")
        small, big = offers
        self.assertEqual(small.get("available"), "true")
        self.assertEqual(small.findtext("stock_quantity"), "3")
        self.assertEqual(big.get("available"), "false")
        self.assertEqual(big.findtext("stock_quantity"), "0")

    def test_url_has_size_and_pictures_are_https_ascii(self):
        offers = self._root().findall("shop/offers/offer")
        for o in offers:
            self.assertTrue(o.findtext("url").startswith("https://mrcarpet24.com/catalog/product/"))
        self.assertTrue(offers[0].findtext("url").endswith(f"?size={self.small.pk}"))
        pictures = [p.text for p in offers[0].findall("picture")]
        self.assertTrue(1 <= len(pictures) <= 15)
        for pic in pictures:
            self.assertTrue(pic.startswith("https://"))
            self.assertTrue(pic.isascii())
            self.assertNotIn(" ", pic)
            self.assertLessEqual(len(pic), 1999)

    def test_category_vendor_description_and_params(self):
        offer = self._root().findall("shop/offers/offer")[0]
        self.assertEqual(offer.findtext("categoryId"), str(self.category.pk))  # room, not country
        self.assertEqual(offer.findtext("vendor"), "Без бренду")  # no brand spec -> fallback
        self.assertTrue(offer.findtext("description").startswith("<p>Мʼякий килимок"))
        self.assertTrue(offer.findtext("description_ua").startswith("<p>Мʼякий килимок"))
        params = {p.get("name"): p.text for p in offer.findall("param")}
        self.assertEqual(params["Розмір"], "60x100 см")
        self.assertEqual(params["Колір"], "фіолетово-ліловий")
        self.assertEqual(params["Форма"], "Прямокутник")
        self.assertEqual(params["Країна-виробник товару"], "Туреччина")
        self.assertEqual(params["Матеріал"], "Поліпропілен")  # Rozetka's own name
        self.assertEqual(params["Висота ворсу"], "6.5 мм")
        self.assertEqual(params["Вид"], "Килими")
        self.assertNotIn("Склад килима", params)
        self.assertNotIn("Виробник", params)  # held a country, clashed with the brand
        for value in params.values():
            self.assertTrue(value)
            self.assertLessEqual(len(value), 500)

    def test_brand_spec_becomes_vendor(self):
        _spec(self.product, "Бренд", "Dinarsu")
        offer = self._root().findall("shop/offers/offer")[0]
        self.assertEqual(offer.findtext("vendor"), "Dinarsu")

    def test_product_without_category_uses_fallback_category(self):
        self.product.categories.clear()
        root = self._root()
        offer = root.find("shop/offers/offer")
        self.assertEqual(offer.findtext("categoryId"), str(ROZETKA_FALLBACK_CATEGORY_ID))
        ids = {c.get("id") for c in root.findall("shop/categories/category")}
        self.assertIn(str(ROZETKA_FALLBACK_CATEGORY_ID), ids)

    def test_every_offer_category_is_declared(self):
        root = self._root()
        ids = {c.get("id") for c in root.findall("shop/categories/category")}
        for o in root.findall("shop/offers/offer"):
            self.assertIn(o.findtext("categoryId"), ids)

    def test_route(self):
        resp = self.client.get("/feeds/rozetka.xml", secure=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/xml", resp["Content-Type"])
        self.assertIn("utf-8", resp["Content-Type"].lower())
        root = ET.fromstring(resp.content)
        self.assertEqual(root.tag, "yml_catalog")
        self.assertEqual(len(root.findall("shop/offers/offer")), 2)


class RozetkaEmptyShopTests(TestCase):
    def test_route_with_no_products(self):
        resp = self.client.get("/feeds/rozetka.xml", secure=True)
        self.assertEqual(resp.status_code, 200)
        root = ET.fromstring(resp.content)
        self.assertEqual(root.findall("shop/offers/offer"), [])


class RozetkaParamsTests(SimpleTestCase):
    def test_spec_names_mapped_and_extras_added(self):
        from project.prom_feed import _rozetka_params

        params = _rozetka_params(
            [("Склад килима", "Поліпропілен"), ("Висота ворса", "6.5 мм"),
             ("Виробник", "Україна"), ("Форма килима", "Овал"), ("Основа", "Джут")],
            "120x170 см", "темно-сірий", "Овал", "Україна",
            kind="Килими", vendor="Karat", rooms=["Для дитячої", "Для кухні"],
            pattern="абстрактний",
        )
        d = dict(params)
        self.assertEqual(len(d), len(params))  # no duplicate names
        self.assertEqual(d["Матеріал"], "Поліпропілен")
        self.assertEqual(d["Висота ворсу"], "6.5 мм")
        self.assertEqual(d["Основний колір"], "Сірий")
        self.assertEqual(d["Країна реєстрації бренду"], "Україна")
        self.assertEqual(d["Призначення"], "Для дитячої, Для кухні")
        self.assertEqual(d["Дизайн"], "Абстрактний")
        self.assertEqual(d["Основа"], "Джут")
        self.assertNotIn("Виробник", d)
        self.assertNotIn("Форма килима", d)

    def test_two_tone_colour_and_unknown_brand_skip_extras(self):
        from project.prom_feed import _rozetka_kind, _rozetka_params

        d = dict(_rozetka_params([], "60x110 см", "сіро-коричневий", "", "", vendor="mr.Carpet"))
        self.assertNotIn("Основний колір", d)
        self.assertNotIn("Країна реєстрації бренду", d)
        self.assertNotIn("Призначення", d)
        self.assertEqual(_rozetka_kind("Килимова доріжка Flex 80 см"), "Килимові доріжки")


class RozetkaDescriptionTests(SimpleTestCase):
    def test_size_list_and_cross_sell_dropped(self):
        from project.prom_feed import rozetka_description

        text = (
            "Сірий прямокутний килим Mira 24058/160. Малюнок абстрактний.\n"
            "Ворс 6.5 мм, основа джутова. Розмірів десять, від 60х110 см до 3х4 м. "
            "Зроблено в Україні.\n"
            "Любите м’якші лінії? Є такий самий овальний."
        )
        out = rozetka_description(text)
        self.assertNotIn("Розмірів", out)
        self.assertNotIn("овальний", out)
        self.assertNotIn("Любите", out)
        self.assertIn("Зроблено в Україні.", out)
        self.assertIn("Ворс 6.5 мм, основа джутова.", out)

    def test_single_size_cut_out_of_sentence(self):
        from project.prom_feed import rozetka_description

        self.assertEqual(
            rozetka_description("Коричневий гумовий килимок під двері, 40х60 см, у формі напівкола."),
            "Коричневий гумовий килимок під двері, у формі напівкола.",
        )
        self.assertEqual(
            rozetka_description("Сірий килимок Taflan для ванної кімнати, розмір 60х100 см."),
            "Сірий килимок Taflan для ванної кімнати.",
        )

    def test_nothing_left_keeps_original(self):
        from project.prom_feed import rozetka_description

        self.assertEqual(rozetka_description("Є два розміри: 60х80 см і 70х120 см."),
                         "Є два розміри: 60х80 см і 70х120 см.")



class ShapeTitleWinsTests(SimpleTestCase):
    def test_title_shape_beats_mistyped_spec(self):
        from types import SimpleNamespace

        from project.merchant_feed import product_shape

        oval = SimpleNamespace(title="Килим овальний Modern GK506 сірий")
        self.assertEqual(product_shape(oval, [("Форма килима", "Прямокутник")], "120x200 см"), "Овал")
        semi = SimpleNamespace(title="Килим напівкруглий під двері гумовий")
        self.assertEqual(product_shape(semi, [("Форма", "Напівколо")], ""), "Напівколо")
        round_ = SimpleNamespace(title="Килим круглий Kids")
        self.assertEqual(product_shape(round_, [("Форма", "Круглий")], ""), "Круглий")


class SpecFixMigrationTests(TestCase):
    def test_fixes_shape_pile_and_rubber(self):
        import importlib

        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        from catalog.models import Product

        oval = Product.objects.create(title="Килим овальний Modern GK506", slug="kilim-ovalnii-sirii-moderngk506-o")
        oksi = Product.objects.create(title="Килим прямокутний Oksi 38025.608", slug="kilim-priamokutnii-oksi-38025608")
        other = Product.objects.create(title="Килим прямокутний", slug="kilim-inshii")
        _spec(oval, "Форма килима", "Прямокутник")
        _spec(other, "Форма килима", "Прямокутник")
        _spec(oksi, "Висота ворса", "Безворсовий")
        _spec(other, "Основа", "Резина")

        apps = MigrationLoader(connection).project_state(
            ("catalog", "0051_fix_specs_for_rozetka")
        ).apps
        mod = importlib.import_module("catalog.migrations.0051_fix_specs_for_rozetka")
        mod.forwards(apps, None)
        mod.forwards(apps, None)  # idempotent

        shape = ProductSpecification.objects.get(product=oval)
        self.assertEqual(shape.spec_value.title, "Овал")
        self.assertEqual(
            ProductSpecification.objects.get(product=other, specification__title="Форма килима").spec_value.title,
            "Прямокутник",
        )
        self.assertIsNone(ProductSpecification.objects.get(product=oksi).spec_value)
        self.assertEqual(
            ProductSpecification.objects.get(product=other, specification__title="Основа").spec_value.title,
            "Гума",
        )
