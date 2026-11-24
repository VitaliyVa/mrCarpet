"""Canonical / SITE_URL helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from django.test import SimpleTestCase, override_settings

from project.seo_urls import (
    absolute_site_url,
    canonical_query,
    canonical_url,
    has_content_query,
    is_tracking_param,
)


def _req(full_path):
    return SimpleNamespace(get_full_path=lambda: full_path)


class SeoUrlsTests(TestCase):
    @override_settings(SITE_URL="https://mrcarpet24.com")
    def test_absolute_site_url(self):
        self.assertEqual(
            absolute_site_url("/product/1/"),
            "https://mrcarpet24.com/product/1/",
        )
        self.assertEqual(
            absolute_site_url("http://evil.com/x"),
            "https://mrcarpet24.com/x",
        )

    @override_settings(SITE_URL="https://mrcarpet24.com")
    def test_canonical_url_from_request(self):
        req = _req("/checkout/?a=1")
        self.assertEqual(
            canonical_url(req),
            "https://mrcarpet24.com/checkout/",
        )


@override_settings(SITE_URL="https://mrcarpet24.com")
class CanonicalQueryTests(SimpleTestCase):
    def test_tracking_params_never_reach_canonical(self):
        for qs in (
            "gclid=abc",
            "fbclid=x&utm_source=fb&utm_medium=cpc",
            "yclid=1",
            "ttclid=1",
            "gbraid=1&wbraid=2&gad_source=1",
            "msclkid=1",
            "srsltid=AfmBOo",
            "_gl=1*abc",
        ):
            self.assertEqual(
                canonical_url(_req(f"/catalog/collection/?{qs}")),
                "https://mrcarpet24.com/catalog/collection/",
                qs,
            )
            self.assertFalse(has_content_query(_req(f"/?{qs}")), qs)

    def test_page_one_has_no_query(self):
        self.assertEqual(
            canonical_url(_req("/catalog/collection/?page=1")),
            "https://mrcarpet24.com/catalog/collection/",
        )

    def test_page_n_is_kept_and_tracking_dropped(self):
        self.assertEqual(
            canonical_url(_req("/catalog/collection/?utm_source=x&page=3&gclid=y")),
            "https://mrcarpet24.com/catalog/collection/?page=3",
        )
        self.assertEqual(canonical_query(_req("/x/?page=2")), "?page=2")

    def test_junk_page_values_are_dropped(self):
        for v in ("abc", "0", "-2", "", "1.5"):
            self.assertEqual(canonical_query(_req(f"/x/?page={v}")), "", v)

    def test_search_points_to_clean_listing(self):
        req = _req("/catalog/?q=%7Bsearch_term_string%7D")
        self.assertTrue(has_content_query(req))
        self.assertEqual(canonical_url(req), "https://mrcarpet24.com/catalog/")

    def test_filter_and_sort_point_to_unfiltered_first_page(self):
        req = _req("/catalog/collection/?sort=price&%D0%9A%D0%BE%D0%BB%D1%96%D1%80=red&page=2")
        self.assertTrue(has_content_query(req))
        self.assertEqual(canonical_query(req), "")
        self.assertEqual(
            canonical_url(req), "https://mrcarpet24.com/catalog/collection/"
        )

    def test_empty_search_still_counts_as_search(self):
        self.assertTrue(has_content_query(_req("/catalog/?q=")))

    def test_clean_and_paginated_urls_are_indexable(self):
        self.assertFalse(has_content_query(_req("/catalog/collection/")))
        self.assertFalse(has_content_query(_req("/catalog/collection/?page=4")))

    def test_tracking_detection_is_case_insensitive(self):
        self.assertTrue(is_tracking_param("UTM_Campaign"))
        self.assertTrue(is_tracking_param("GCLID"))
        self.assertFalse(is_tracking_param("q"))
        self.assertFalse(is_tracking_param("page"))


class ProductSizeParamTests(TestCase):
    def _req(self, url):
        from django.test import RequestFactory
        return RequestFactory().get(url)

    def test_size_on_product_page_stays_indexable_and_clean(self):
        from project.seo_urls import canonical_url, has_content_query
        r = self._req("/catalog/product/foo/?size=482&gclid=x")
        self.assertFalse(has_content_query(r))
        self.assertTrue(canonical_url(r).endswith("/catalog/product/foo/"))

    def test_size_on_listing_is_a_filter(self):
        from project.seo_urls import has_content_query
        self.assertTrue(has_content_query(self._req("/catalog/collection/?size=3")))
