"""Unit tests for GA4 chart rendering (no live API)."""

from __future__ import annotations

from unittest import TestCase

from project.ga4_charts import (
    build_caption,
    build_dashboard_photos,
    render_funnel_chart,
    render_kpi_table,
    render_realtime_chart,
    render_sources_chart,
)


class Ga4ChartsTests(TestCase):
    def test_funnel_png(self):
        blob = render_funnel_chart(
            [
                {"event": "view_item", "events": 10, "users": 5},
                {"event": "purchase", "events": 1, "users": 1},
            ],
            days=7,
        )
        self.assertTrue(blob.startswith(b"\x89PNG"))
        self.assertGreater(len(blob), 2000)

    def test_sources_and_kpi(self):
        src = render_sources_chart(
            [{"source": "google", "medium": "organic", "sessions": 12, "purchases": 1}],
            days=7,
        )
        kpi = render_kpi_table(
            {
                "activeUsers": "3",
                "sessions": "4",
                "pageViews": "10",
                "engagedSessions": "2",
            },
            {
                "purchaseRevenue": "1500",
                "ecommercePurchases": "1",
                "averagePurchaseRevenue": "1500",
            },
            days=7,
            top_pages=[{"path": "/", "views": "5", "users": "2"}],
        )
        self.assertTrue(src.startswith(b"\x89PNG"))
        self.assertTrue(kpi.startswith(b"\x89PNG"))

    def test_dashboard_bundle(self):
        photos = build_dashboard_photos(
            {
                "days": 7,
                "funnel": [{"event": "view_item", "events": 2, "users": 1}],
                "sources": [],
                "kpis": {"activeUsers": "1", "sessions": "1", "pageViews": "1", "engagedSessions": "1"},
                "revenue": {
                    "purchaseRevenue": "0",
                    "ecommercePurchases": "0",
                    "averagePurchaseRevenue": "0",
                },
                "top_pages": [],
            }
        )
        self.assertEqual(len(photos), 3)
        caption = build_caption(
            {
                "days": 7,
                "kpis": {"activeUsers": "1", "sessions": "2", "pageViews": "3"},
                "revenue": {"ecommercePurchases": "0", "purchaseRevenue": "0"},
                "funnel": [{"event": "purchase", "events": 0}],
            }
        )
        self.assertIn("GA4", caption)
        self.assertIn("7", caption)

    def test_realtime_png(self):
        blob = render_realtime_chart(
            {"active_users": 2, "screens": [{"screen": "Home", "users": 2}]}
        )
        self.assertTrue(blob.startswith(b"\x89PNG"))
