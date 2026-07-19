"""Unit tests for GA4 Measurement Protocol helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from django.test import override_settings

from project.ga4_mp import (
    client_id_from_ga_cookie,
    mp_configured,
    send_mp_purchase,
)


class Ga4MpHelpersTests(TestCase):
    def test_client_id_from_ga_cookie(self):
        self.assertEqual(
            client_id_from_ga_cookie("GA1.1.1234567890.1234567890"),
            "1234567890.1234567890",
        )
        self.assertIsNone(client_id_from_ga_cookie(""))
        self.assertIsNone(client_id_from_ga_cookie(None))

    @override_settings(GA4_MEASUREMENT_ID="G-TEST", GA4_API_SECRET="secret")
    def test_mp_configured(self):
        self.assertTrue(mp_configured())

    @override_settings(GA4_MEASUREMENT_ID="", GA4_API_SECRET="")
    def test_mp_not_configured(self):
        self.assertFalse(mp_configured())

    @override_settings(GA4_MEASUREMENT_ID="G-TEST", GA4_API_SECRET="secret")
    @patch("project.ga4_mp.requests.post")
    def test_send_mp_purchase_ok(self, mock_post):
        mock_post.return_value = SimpleNamespace(status_code=204, text="", content=b"")
        ok = send_mp_purchase(
            {
                "transaction_id": "999",
                "currency": "UAH",
                "value": 100,
                "items": [
                    {
                        "item_id": "1",
                        "item_name": "A",
                        "price": 100,
                        "quantity": 1,
                    }
                ],
            },
            client_id="1.2",
        )
        self.assertTrue(ok)
        self.assertTrue(mock_post.called)
        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get(
            "json"
        )
        if body is None:
            body = mock_post.call_args[0][1] if len(mock_post.call_args[0]) > 1 else None
        # requests.post(url, json=body)
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(kwargs["json"]["events"][0]["name"], "purchase")
        self.assertEqual(
            kwargs["json"]["events"][0]["params"]["transaction_id"], "999"
        )
