"""Tests for Phase 8 indexing switch (must stay OFF by default)."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from project.seo_indexing import build_robots_txt, is_indexing_enabled


class SeoIndexingSwitchTests(SimpleTestCase):
    @override_settings(SEO_INDEXING_ENABLED=False)
    def test_default_robots_disallow_all(self):
        self.assertFalse(is_indexing_enabled())
        body = build_robots_txt()
        self.assertIn("Disallow: /", body)
        self.assertNotIn("Allow: /", body)

    @override_settings(SEO_INDEXING_ENABLED=True)
    def test_prod_robots_allow_with_private_disallow(self):
        self.assertTrue(is_indexing_enabled())
        body = build_robots_txt(sitemap_url="https://mrcarpet24.com/sitemap.xml")
        lines = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertIn("Allow: /", lines)
        self.assertIn("Disallow: /admin/", lines)
        self.assertIn("Disallow: /basket/", lines)
        self.assertIn("Disallow: /checkout/", lines)
        self.assertIn("Disallow: /success/", lines)
        self.assertIn("Sitemap: https://mrcarpet24.com/sitemap.xml", lines)
        self.assertNotIn("Disallow: /", lines)
