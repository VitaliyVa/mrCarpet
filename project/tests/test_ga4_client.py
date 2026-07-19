"""Unit tests for GA4 client helpers (mocked HTTP)."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from django.test import override_settings

from project.ga4_client import (
    Ga4ClientError,
    _metric_row,
    fetch_overview,
    ga4_configured,
)


class Ga4ClientTests(TestCase):
    def test_metric_row_empty(self):
        out = _metric_row({}, ["a", "b"])
        self.assertEqual(out, {"a": "0", "b": "0"})

    def test_metric_row_values(self):
        resp = {
            "rows": [
                {
                    "metricValues": [
                        {"value": "10"},
                        {"value": "20"},
                    ]
                }
            ]
        }
        out = _metric_row(resp, ["activeUsers", "sessions"])
        self.assertEqual(out["activeUsers"], "10")
        self.assertEqual(out["sessions"], "20")

    @override_settings(GA4_PROPERTY_ID="", GA4_SERVICE_ACCOUNT_JSON="")
    def test_not_configured(self):
        self.assertFalse(ga4_configured())

    @override_settings(
        GA4_PROPERTY_ID="546178687",
        GA4_SERVICE_ACCOUNT_JSON='{"client_email":"a@b.com","private_key":"x"}',
    )
    def test_configured_flag(self):
        self.assertTrue(ga4_configured())

    @override_settings(
        GA4_PROPERTY_ID="546178687",
        GA4_SERVICE_ACCOUNT_JSON='{"client_email":"a@b.com","private_key":"x"}',
    )
    @patch("project.ga4_client.api_json")
    def test_fetch_overview_parses(self, mock_api):
        mock_api.side_effect = [
            {
                "rows": [
                    {
                        "metricValues": [
                            {"value": "5"},
                            {"value": "6"},
                            {"value": "7"},
                            {"value": "8"},
                        ]
                    }
                ]
            },
            {
                "rows": [
                    {
                        "dimensionValues": [{"value": "/"}],
                        "metricValues": [{"value": "3"}, {"value": "2"}],
                    }
                ]
            },
        ]
        data = fetch_overview(7)
        self.assertEqual(data["kpis"]["activeUsers"], "5")
        self.assertEqual(data["top_pages"][0]["path"], "/")

    @override_settings(GA4_PROPERTY_ID="bad", GA4_SERVICE_ACCOUNT_JSON="{}")
    def test_bad_property(self):
        with self.assertRaises(Ga4ClientError):
            fetch_overview(7)
