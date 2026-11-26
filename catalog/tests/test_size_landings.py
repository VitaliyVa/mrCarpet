"""
Size landings: /catalog/rozmir/160x230/.

"килим 160х230" is a real query, but the only listing for a size was the
facet ?size=<id>: noindex, canonical to the whole collection. These pages
give each popular size one indexable URL, built from the real Size rows
(metres, Cyrillic or Latin x, duplicates merged), and only while enough
products are in stock in that size.
"""

import json
import re

from django.test import TestCase, override_settings

from catalog import size_landings as sl
from catalog.models import (
    Product,
    ProductAttribute,
    ProductCategory,
    ProductSpecification,
    Size,
    Specification,
    SpecificationValue,
)

SITE = "https://mrcarpet24.com"
INDEX_ROBOTS = "index, follow, max-image-preview:large, max-snippet:-1"
PATH = "/catalog/rozmir/160x230/"


def _canonical(html):
    m = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return m and m.group(1)


def _og_url(html):
    m = re.search(r'<meta property="og:url" content="([^"]*)"', html)
    return m and m.group(1)


def _robots(html):
    m = re.search(r'<meta name="robots" content="([^"]*)"', html)
    return m and m.group(1)


def _title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m and m.group(1).strip()


def _description(html):
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html, re.S)
    return m and m.group(1)


def _h1(html):
    m = re.search(r'<h1 class="catalog_inside__title">\s*(.*?)\s*</h1>', html, re.S)
    return m and m.group(1)


class SizeSlugTests(TestCase):
    def test_real_size_titles_normalise(self):
        self.assertEqual(sl.size_title_slug("1.6х2.3"), "160x230")  # Cyrillic х
        self.assertEqual(sl.size_title_slug("1.6x2.3"), "160x230")
        self.assertEqual(sl.size_title_slug("0.45х0.75"), "45x75")
        self.assertEqual(sl.size_title_slug("160x230 см"), "160x230")
        self.assertEqual(sl.size_title_slug("160 x 230"), "160x230")

    def test_orientation_does_not_make_a_second_page(self):
        self.assertEqual(sl.size_title_slug("4.0x2.0"), "200x400")
        self.assertEqual(sl.size_title_slug("2.0х4.0"), "200x400")

    def test_not_a_rectangle_has_no_slug(self):
        for title in ("∅ 67 см", "на відріз", "M", "Великий", "", None):
            self.assertIsNone(sl.size_title_slug(title), title)

    def test_url_part_parsing(self):
        self.assertEqual(sl.parse_slug("160x230"), "160x230")
        self.assertEqual(sl.parse_slug("230x160"), "160x230")
        self.assertEqual(sl.parse_slug("160Х230"), "160x230")
        self.assertEqual(sl.parse_slug("160х230"), "160x230")
        for bad in ("abc", "1.6x2.3", "160", "160x230x5", "1x2", ""):
            self.assertIsNone(sl.parse_slug(bad), bad)


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
class SizeLandingPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from project.models import ShopSettings

        shop = ShopSettings.load()
        shop.free_shipping_enabled = True
        shop.free_shipping_threshold = 1499
        shop.save()

        # The same size twice, as on the live site ("1.2x2.0" / "1.2х2.0").
        cls.size_cyr = Size.objects.create(title="1.6х2.3")
        cls.size_lat = Size.objects.create(title="1.6x2.3")
        cls.small = Size.objects.create(title="0.8х1.5")
        cls.rare = Size.objects.create(title="2.0х3.0")

        material = Specification.objects.create(title="Склад килима")
        pp = SpecificationValue.objects.create(title="Поліпропілен", specification=material)
        pe = SpecificationValue.objects.create(title="Поліестер", specification=material)
        country = Specification.objects.create(title="Виробник")
        tr = SpecificationValue.objects.create(title="Турція", specification=country)

        cls.cat = ProductCategory.objects.create(title="Турецькі", slug="turetski")
        cls.other_cat = ProductCategory.objects.create(title="Для ванни", slug="dlia-vanny")

        cls.products = []
        cls.landing_attrs = {}
        # 13 in stock in 160x230 -> 2 pages of 12
        for i in range(13):
            p = Product.objects.create(title=f"Килим {i}", slug=f"kylym-size-{i}")
            ProductAttribute.objects.create(
                product=p, size=cls.small, price=500 + i, quantity=2, sort_order=0
            )
            attr = ProductAttribute.objects.create(
                product=p,
                size=cls.size_cyr if i % 2 else cls.size_lat,
                price=2000 + i,
                discount=10 if i == 0 else None,
                quantity=1,
                sort_order=1,
            )
            cls.landing_attrs[p.pk] = attr
            ProductSpecification.objects.create(
                product=p, specification=material, spec_value=pp if i < 9 else pe
            )
            ProductSpecification.objects.create(product=p, specification=country, spec_value=tr)
            p.categories.add(cls.cat)
            cls.products.append(p)

        # In the size but sold out there: must not count or show.
        cls.sold_out = Product.objects.create(title="Розпроданий", slug="rozprodanyi")
        ProductAttribute.objects.create(
            product=cls.sold_out, size=cls.small, price=700, quantity=3
        )
        ProductAttribute.objects.create(
            product=cls.sold_out, size=cls.size_cyr, price=100, quantity=0
        )

        # Only 5 in 200x300: below the minimum, no page.
        for i in range(5):
            p = Product.objects.create(title=f"Рідкий {i}", slug=f"ridkyi-{i}")
            ProductAttribute.objects.create(product=p, size=cls.rare, price=3000, quantity=1)
            p.categories.add(cls.other_cat)

    def get(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, url)
        return resp.content.decode()

    # --- the page ----------------------------------------------------------

    def test_landing_is_indexable_with_own_canonical(self):
        html = self.get(PATH)
        self.assertEqual(_robots(html), INDEX_ROBOTS)
        self.assertEqual(_canonical(html), SITE + PATH)
        self.assertEqual(_og_url(html), SITE + PATH)

    def test_h1_title_description(self):
        html = self.get(PATH)
        self.assertEqual(_h1(html), "Килими 160x230 см")
        # 2000 - 10% = 1800, the cheapest in this size (not the 500 small one)
        self.assertEqual(
            _title(html),
            "Килими 160x230 см: купити в Україні, ціни від 1800 грн | mr.Carpet",
        )
        desc = _description(html)
        self.assertIn("13 моделей", desc)
        self.assertIn("ціни від 1800 грн", desc)
        self.assertIn("Поліпропілен і поліестер.", desc)
        self.assertIn("безкоштовно від 1499 грн", desc)

    def test_intro_is_built_from_real_data(self):
        html = self.get(PATH)
        intro = re.search(r'<p class="catalog_intro">(.*?)</p>', html, re.S).group(1)
        self.assertIn("Ширина 160 см, довжина 230 см.", intro)
        self.assertIn("13 моделей, ціни від 1800 грн.", intro)
        self.assertIn("Матеріали: поліпропілен і поліестер.", intro)
        self.assertIn("Виробництво: Турція.", intro)
        self.assertIn("Доставка по Україні безкоштовна від 1499 грн.", intro)

    def test_texts_have_no_dashes(self):
        landing = sl.get_landing("160x230")
        for text in (
            sl.landing_intro(landing),
            sl.landing_meta_description(landing),
            sl.landing_meta_title(landing),
            sl.landing_h1(landing),
        ):
            self.assertNotIn("—", text)
            self.assertNotIn("–", text)
            self.assertNotIn(" - ", text)

    def test_duplicate_size_rows_are_one_page(self):
        landing = sl.get_landing("160x230")
        self.assertEqual(set(landing.size_ids), {self.size_cyr.pk, self.size_lat.pk})
        self.assertEqual(landing.count, 13)

    def test_sold_out_product_is_not_listed(self):
        html = self.get(PATH) + self.get(PATH + "?page=2")
        self.assertNotIn(self.sold_out.get_absolute_url(), html)
        self.assertEqual(sl.get_landing("160x230").price_from, 1800)

    def test_cards_open_on_the_landing_size(self):
        html = self.get(PATH)
        p = self.products[-1]  # newest first
        attr = self.landing_attrs[p.pk]
        self.assertIn(f'href="{p.get_absolute_url()}?size={attr.pk}"', html)
        self.assertIn(f'data-product-id="{attr.pk}" data-catalog-product-id="{p.pk}"', html)

    def test_breadcrumbs(self):
        html = self.get(PATH)
        graphs = [
            json.loads(block)
            for block in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>', html, re.S
            )
        ]
        data = next(g for g in graphs if g.get("@type") == "BreadcrumbList")
        items = data["itemListElement"]
        self.assertEqual(items[-1]["name"], "Килими 160x230 см")
        self.assertEqual(items[-1]["item"], SITE + PATH)

    def test_size_facet_is_hidden_on_the_landing(self):
        html = self.get(PATH)
        self.assertNotIn('<input type="checkbox" name="size"', html)
        # the other facets are still there
        self.assertIn('<input type="checkbox" name="склад килима"', html)

    # --- pagination ----------------------------------------------------------

    def test_page_two_is_its_own_canonical(self):
        html = self.get(PATH + "?page=2")
        self.assertEqual(_canonical(html), SITE + PATH + "?page=2")
        self.assertEqual(_og_url(html), SITE + PATH + "?page=2")
        self.assertEqual(_robots(html), INDEX_ROBOTS)
        self.assertIn(", сторінка 2 | mr.Carpet", _title(html))
        self.assertNotIn('class="catalog_intro"', html)

    def test_page_past_the_end_is_404(self):
        resp = self.client.get(PATH + "?page=99")
        self.assertEqual(resp.status_code, 404)

    def test_tracking_params_do_not_change_the_page(self):
        html = self.get(PATH + "?gclid=abc&utm_source=google")
        self.assertEqual(_robots(html), INDEX_ROBOTS)
        self.assertEqual(_canonical(html), SITE + PATH)

    # --- noindex rules -------------------------------------------------------

    def test_filters_and_sort_on_the_landing_are_noindex(self):
        for query in ({"sort": "price"}, {"size": self.small.pk}, {"склад килима": "Поліестер"}):
            resp = self.client.get(PATH, query)
            self.assertEqual(resp.status_code, 200, query)
            html = resp.content.decode()
            self.assertEqual(_robots(html), "noindex, follow", query)
            self.assertEqual(_canonical(html), SITE + PATH, query)

    def test_size_facet_on_collection_stays_noindex(self):
        html = self.get("/catalog/collection/?size=%d" % self.size_cyr.pk)
        self.assertEqual(_robots(html), "noindex, follow")
        self.assertEqual(_canonical(html), SITE + "/catalog/collection/")

    # --- what has no page ----------------------------------------------------

    def test_rare_size_is_404(self):
        self.assertEqual(self.client.get("/catalog/rozmir/200x300/").status_code, 404)

    def test_unknown_and_garbage_sizes_are_404(self):
        for url in (
            "/catalog/rozmir/999x999/",
            "/catalog/rozmir/abc/",
            "/catalog/rozmir/1.6x2.3/",
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_every_size_with_enough_stock_has_a_page(self):
        """80x150: 13 + the one sold out in 160x230 but in stock here."""
        self.assertEqual(sl.get_landing("80x150").count, 14)
        self.assertEqual(self.client.get("/catalog/rozmir/80x150/").status_code, 200)

    def test_page_disappears_when_stock_drops_below_the_minimum(self):
        ProductAttribute.objects.filter(
            size__in=[self.size_cyr, self.size_lat], product__in=self.products[5:]
        ).update(quantity=0)
        self.assertEqual(self.client.get(PATH).status_code, 404)

    # --- one URL per size ----------------------------------------------------

    def test_other_spellings_redirect_to_the_canonical_url(self):
        for url in (
            "/catalog/rozmir/230x160/",
            "/catalog/rozmir/160X230/",
            "/catalog/rozmir/160%D1%85230/",  # Cyrillic х
        ):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 301, url)
            self.assertEqual(resp["Location"], PATH, url)

    def test_redirect_keeps_the_query(self):
        resp = self.client.get("/catalog/rozmir/230x160/?page=2")
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp["Location"], PATH + "?page=2")

    # --- sitemap ---------------------------------------------------------------

    def test_sitemap_lists_only_sizes_with_a_page(self):
        xml = self.get("/sitemap.xml")
        self.assertIn(f"<loc>{SITE}{PATH}</loc>", xml)
        self.assertIn(f"<loc>{SITE}/catalog/rozmir/80x150/</loc>", xml)
        self.assertNotIn("/catalog/rozmir/200x300/", xml)

    def test_sitemap_uses_site_url_not_request_host(self):
        resp = self.client.get("/sitemap.xml", HTTP_HOST="www.mrcarpet24.com")
        xml = resp.content.decode()
        self.assertNotIn("www.mrcarpet24.com", xml)
        self.assertNotIn("http://", xml.replace("http://www.sitemaps.org", "").replace("http://www.w3.org", ""))
        self.assertIn(f"<loc>{SITE}/catalog/</loc>", xml)

    # --- internal links ------------------------------------------------------

    def test_category_page_links_to_its_sizes(self):
        html = self.get("/catalog/categorie/turetski/")
        self.assertIn('aria-label="Популярні розміри"', html)
        self.assertIn(f'href="{PATH}"', html)
        self.assertIn('href="/catalog/rozmir/80x150/"', html)

    def test_category_without_those_sizes_shows_no_chips(self):
        html = self.get("/catalog/categorie/dlia-vanny/")
        self.assertNotIn('aria-label="Популярні розміри"', html)

    def test_collection_links_to_size_pages(self):
        html = self.get("/catalog/collection/")
        self.assertIn(f'href="{PATH}"', html)
        self.assertNotIn('href="/catalog/rozmir/200x300/"', html)

    def test_landing_links_to_other_sizes_not_itself(self):
        html = self.get(PATH)
        nav = re.search(r'<nav class="size_chips".*?</nav>', html, re.S).group(0)
        self.assertIn('href="/catalog/rozmir/80x150/"', nav)
        self.assertNotIn(f'href="{PATH}"', nav)

    def test_chips_sorted_small_to_large(self):
        chips = sl.popular_sizes()
        self.assertEqual([c.slug for c in chips], ["80x150", "160x230"])
