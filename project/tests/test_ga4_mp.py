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


class SingleSourceOfTruthTests(TestCase):
    """
    Purchase is reported from exactly one place.

    It used to fire from two: the browser on /success/ and the server via
    Measurement Protocol. Each deduped against itself — sessionStorage on one
    side, Order.ga4_mp_sent on the other — and neither knew about the other,
    so every sale that completed normally was counted twice at double the
    revenue.
    """

    def test_success_page_does_not_send_a_purchase(self):
        from pathlib import Path

        html = Path("templates/success.html").read_text(encoding="utf-8")
        self.assertNotIn('gtag("event", "purchase"', html)
        self.assertNotIn('event: "purchase"', html)

    def test_success_page_does_not_reload_itself(self):
        """The reload existed only to wait out the LiqPay callback race so the
        browser could fire the event. The callback now sends it."""
        from pathlib import Path

        html = Path("templates/success.html").read_text(encoding="utf-8")
        self.assertNotIn("window.location.reload", html)


class CardAttributionTests(TestCase):
    """
    A card purchase must carry the client_id captured at checkout.

    Without it client_id_for_order falls back to a hash of the order number,
    which GA4 reads as a visitor it has never seen — so the sale is attributed
    to "direct" rather than to whatever brought the buyer.
    """

    def test_liqpay_callback_passes_the_stored_client_id(self):
        import inspect

        from payment import utils

        source = inspect.getsource(utils)
        self.assertIn("enqueue_order_purchase_mp(order.pk, client_id=", source)
        self.assertIn("ga4_client_id", source)

    def test_checkout_stores_the_client_id_for_both_payment_types(self):
        import inspect

        from order.api import views

        source = inspect.getsource(views)
        captured = source.index("cid = client_id_from_ga_cookie")
        stored = source.index("ga4_client_id=cid")
        self.assertLess(captured, stored)

        # The whole point: nothing may gate the store on payment type.
        # Scoped to the span between capture and store, because PAYMENT_CASH
        # legitimately appears elsewhere in this module.
        between = source[captured:stored]
        self.assertNotIn(
            "PAYMENT_CASH",
            between,
            "storing the client_id must not be inside the cash-only branch, "
            "otherwise card orders never get one",
        )
