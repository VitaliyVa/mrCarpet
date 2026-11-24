"""
Listing pages must not mint indexable duplicates.

Before: canonical was built from the full request path, so /catalog/?q=test,
every filter/sort combo and every ad click (?gclid=, ?utm_*) declared itself
canonical and `index, follow`. Search Console also filed /catalog/stock/ as a
duplicate of /catalog/ (same template, same content, own canonical).
"""

import re

from django.test import TestCase, override_settings

from catalog.models import Product, ProductAttribute, ProductCategory, Size

SITE = "https://mrcarpet24.com"


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


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
class ListingSeoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = ProductCategory.objects.create(title="Турецькі", slug="turetski")
        cls.size = size = Size.objects.create(title="1.6 x 2.3")
        # 13 buyable products -> 2 pages of 12
        for i in range(13):
            p = Product.objects.create(title=f"Килим {i}", slug=f"kylym-seo-{i}")
            ProductAttribute.objects.create(
                product=p, size=size, price=1000 + i, quantity=3
            )
            p.categories.add(cls.cat)

    def get(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, url)
        return resp.content.decode()

    def test_search_on_catalog_is_noindex_and_canonical_clean(self):
        html = self.get("/catalog/?q={search_term_string}")
        self.assertEqual(_robots(html), "noindex, follow")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/")
        self.assertEqual(_og_url(html), f"{SITE}/catalog/")

    def test_search_on_collection_is_noindex(self):
        html = self.get("/catalog/collection/?q=test")
        self.assertEqual(_robots(html), "noindex, follow")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/collection/")

    def test_stock_canonicalizes_to_catalog(self):
        html = self.get("/catalog/stock/")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/")
        self.assertEqual(_og_url(html), f"{SITE}/catalog/")
        # one signal only: canonical, not noindex on top
        self.assertEqual(_robots(html), "index, follow")

    def test_catalog_page_param_does_not_split_it(self):
        """/catalog/ renders categories, not the paginated list."""
        html = self.get("/catalog/?page=2")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/")

    def test_ad_click_stays_indexable_with_clean_canonical(self):
        url = "/catalog/collection/?gclid=abc&utm_source=google&utm_medium=cpc&fbclid=z"
        html = self.get(url)
        self.assertEqual(_robots(html), "index, follow")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/collection/")
        cat_url = self.cat.get_absolute_url()
        html = self.get(cat_url + "?gclid=abc")
        self.assertEqual(_canonical(html), f"{SITE}{cat_url}")
        self.assertNotIn("gclid", html.split("</head>")[0])

    def test_ad_click_on_home_has_clean_canonical(self):
        html = self.get("/?gclid=abc&utm_campaign=launch")
        self.assertEqual(_canonical(html), f"{SITE}/")
        self.assertEqual(_og_url(html), f"{SITE}/")
        self.assertEqual(_robots(html), "index, follow")

    def test_page_one_has_no_page_param(self):
        html = self.get("/catalog/collection/?page=1")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/collection/")
        self.assertNotIn("сторінка", _title(html))

    def test_page_two_is_self_canonical_with_unique_title(self):
        html = self.get("/catalog/collection/?page=2")
        self.assertEqual(_robots(html), "index, follow")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/collection/?page=2")
        self.assertEqual(_og_url(html), f"{SITE}/catalog/collection/?page=2")
        self.assertIn("сторінка 2", _title(html))

        cat_url = self.cat.get_absolute_url()
        html = self.get(cat_url + "?page=2&utm_source=x")
        self.assertEqual(_robots(html), "index, follow")
        self.assertEqual(_canonical(html), f"{SITE}{cat_url}?page=2")
        self.assertIn("сторінка 2", _title(html))

    def test_out_of_range_page_uses_real_page_number(self):
        html = self.get("/catalog/collection/?page=999")
        self.assertEqual(_canonical(html), f"{SITE}/catalog/collection/?page=2")

    def test_filter_and_sort_are_noindex_pointing_to_unfiltered(self):
        cat_url = self.cat.get_absolute_url()
        for qs in (
            "sort=price",
            "sort=-title&page=2",
            "price_min=100&price_max=5000",
            f"size={self.size.pk}",
        ):
            html = self.get(f"{cat_url}?{qs}")
            self.assertEqual(_robots(html), "noindex, follow", qs)
            self.assertEqual(_canonical(html), f"{SITE}{cat_url}", qs)
            html = self.get(f"/catalog/collection/?{qs}")
            self.assertEqual(_robots(html), "noindex, follow", qs)
            self.assertEqual(_canonical(html), f"{SITE}/catalog/collection/", qs)

    def test_listing_titles_are_distinct(self):
        titles = {
            _title(self.get("/catalog/")),
            _title(self.get("/catalog/collection/")),
            _title(self.get(self.cat.get_absolute_url())),
        }
        self.assertEqual(len(titles), 3, titles)

    @override_settings(SEO_INDEXING_ENABLED=False)
    def test_indexing_off_still_blocks_everything(self):
        html = self.get("/catalog/collection/?q=test")
        self.assertEqual(_robots(html), "noindex, nofollow")
        html = self.get("/catalog/collection/")
        self.assertEqual(_robots(html), "noindex, nofollow")


class SizeFilterGarbageTests(TestCase):
    def test_text_size_param_does_not_500(self):
        resp = self.client.get("/catalog/collection/?size=60x100")
        self.assertEqual(resp.status_code, 200)
