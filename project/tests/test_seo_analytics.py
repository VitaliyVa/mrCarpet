"""Tests for Phase 9 analytics gating."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from project.seo_analytics import analytics_context, analytics_enabled


class SeoAnalyticsTests(SimpleTestCase):
    @override_settings(
        GA4_MEASUREMENT_ID="",
        GTM_CONTAINER_ID="",
        GOOGLE_SITE_VERIFICATION="",
    )
    def test_disabled_when_empty(self):
        self.assertFalse(analytics_enabled())
        ctx = analytics_context()
        self.assertFalse(ctx["analytics_enabled"])
        self.assertEqual(ctx["ga4_measurement_id"], "")
        self.assertEqual(ctx["gtm_container_id"], "")

    @override_settings(GA4_MEASUREMENT_ID="G-TEST123", GTM_CONTAINER_ID="")
    def test_ga4_enables(self):
        self.assertTrue(analytics_enabled())
        self.assertEqual(analytics_context()["ga4_measurement_id"], "G-TEST123")

    @override_settings(GA4_MEASUREMENT_ID="", GTM_CONTAINER_ID="GTM-TEST")
    def test_gtm_enables(self):
        self.assertTrue(analytics_enabled())
        self.assertEqual(analytics_context()["gtm_container_id"], "GTM-TEST")

    @override_settings(GOOGLE_SITE_VERIFICATION="abc123")
    def test_site_verification_passthrough(self):
        self.assertEqual(analytics_context()["google_site_verification"], "abc123")
