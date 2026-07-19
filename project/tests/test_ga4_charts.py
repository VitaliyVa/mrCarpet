"""Unit tests for GA4 chart rendering (no live API)."""

from __future__ import annotations

from unittest import TestCase

from project.ga4_charts import (
    _friendly_path,
    _human_source,
    build_caption,
    build_dashboard_photos,
    render_funnel_chart,
    render_kpi_table,
    render_realtime_chart,
    render_sources_chart,
)


class Ga4ChartsTests(TestCase):
    def test_human_labels(self):
        self.assertEqual(_human_source("(not set)", "(not set)"), "Прямі / невідомі")
        self.assertEqual(_friendly_path("/"), "Головна")
        self.assertTrue(_friendly_path("/catalog/product/foo").startswith("Товар"))

    def test_funnel_png(self):
        blob = render_funnel_chart(
            [
                {"event": "view_item", "events": 10, "users": 5},
                {"event": "purchase", "events": 1, "users": 1},
            ],
            days=7,
        )
        self.assertTrue(blob.startswith(b"\x89PNG"))
        self.assertGreater(len(blob), 5000)

    def test_sources_and_kpi(self):
        src = render_sources_chart(
            [{"source": "(not set)", "medium": "(not set)", "sessions": 12, "purchases": 1}],
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
            top_pages=[
                {"path": "/", "views": "5", "users": "2"},
                {"path": "/checkout/", "views": "0", "users": "0"},
            ],
        )
        self.assertTrue(src.startswith(b"\x89PNG"))
        self.assertTrue(kpi.startswith(b"\x89PNG"))

    def test_dashboard_bundle(self):
        photos = build_dashboard_photos(
            {
                "days": 7,
                "funnel": [{"event": "view_item", "events": 2, "users": 1}],
                "sources": [],
                "daily": [
                    {"label": "01.07", "users": 1, "sessions": 2, "views": 3},
                    {"label": "02.07", "users": 2, "sessions": 2, "views": 4},
                ],
                "kpis": {
                    "activeUsers": "1",
                    "sessions": "1",
                    "pageViews": "1",
                    "engagedSessions": "1",
                },
                "revenue": {
                    "purchaseRevenue": "0",
                    "ecommercePurchases": "0",
                    "averagePurchaseRevenue": "0",
                },
                "top_pages": [{"path": "/", "views": "2", "users": "1"}],
            }
        )
        self.assertEqual(len(photos), 7)
        self.assertTrue(photos[0][0].startswith("01_"))
        for _name, blob in photos:
            self.assertTrue(blob.startswith(b"\x89PNG"))
        caption = build_caption(
            {
                "days": 7,
                "kpis": {"activeUsers": "1", "sessions": "2", "pageViews": "3"},
                "revenue": {"ecommercePurchases": "0", "purchaseRevenue": "0"},
                "funnel": [{"event": "purchase", "events": 0}],
            }
        )
        self.assertIn("7 слайдів", caption)

    def test_realtime_png(self):
        blob = render_realtime_chart(
            {"active_users": 2, "screens": [{"screen": "Home", "users": 2}]}
        )
        self.assertTrue(blob.startswith(b"\x89PNG"))
