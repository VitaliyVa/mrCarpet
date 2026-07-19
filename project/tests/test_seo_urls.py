"""Canonical / SITE_URL helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from django.test import override_settings

from project.seo_urls import absolute_site_url, canonical_url


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
        req = SimpleNamespace(get_full_path=lambda: "/checkout/?a=1")
        self.assertEqual(
            canonical_url(req),
            "https://mrcarpet24.com/checkout/?a=1",
        )
