"""
Google Customer Reviews opt-in on /success/.

Shown once, for the order this browser just placed, and only when that order
has an email: the survey goes to the buyer's inbox, so without one there is
nothing to offer.
"""

import datetime
import json
import re

from django.test import TestCase, override_settings
from django.utils import timezone

from order.models import Order
from project.customer_reviews import (
    DELIVERY_DAYS,
    SESSION_KEY,
    optin_payload,
)

SNIPPET = "apis.google.com/js/platform.js?onload=renderOptIn"


def _order(**kw):
    data = {
        "name": "Оксана",
        "surname": "Петренко",
        "email": "buyer@example.com",
        "phone": "+380961112233",
        "payment_type": Order.PAYMENT_CASH,
        "status": Order.STATUS_NEW,
    }
    data.update(kw)
    return Order.objects.create(**data)


class PayloadTests(TestCase):
    def test_payload_has_what_google_asks_for(self):
        order = _order()
        Order.objects.filter(pk=order.pk).update(
            created=datetime.datetime(2026, 11, 20, 10, 0, tzinfo=datetime.timezone.utc)
        )
        order.refresh_from_db()
        data = optin_payload(order)
        self.assertEqual(data["merchant_id"], 5860587323)
        self.assertEqual(data["email"], "buyer@example.com")
        self.assertEqual(data["delivery_country"], "UA")
        self.assertEqual(data["estimated_delivery_date"], "2026-11-25")
        self.assertEqual(data["order_id"], str(order.order_number or order.pk))

    def test_delivery_is_five_days_out(self):
        self.assertEqual(DELIVERY_DAYS, 5)

    def test_no_email_means_no_optin(self):
        self.assertIsNone(optin_payload(_order(email="")))
        self.assertIsNone(optin_payload(_order(email="x1@temp.com")))

    @override_settings(GOOGLE_MERCHANT_ID="")
    def test_empty_merchant_id_turns_it_off(self):
        self.assertIsNone(optin_payload(_order()))


class SuccessPageTests(TestCase):
    def _visit(self, order):
        session = self.client.session
        session[SESSION_KEY] = order.pk
        session.save()
        return self.client.get("/success/").content.decode()

    def _data(self, html):
        match = re.search(
            r'<script id="gcr-optin-data" type="application/json">(.*?)</script>',
            html,
            re.S,
        )
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def test_snippet_rendered_for_order_with_email(self):
        order = _order()
        html = self._visit(order)
        self.assertIn(SNIPPET, html)
        data = self._data(html)
        self.assertEqual(data["email"], "buyer@example.com")
        expected = (
            timezone.localdate(order.created) + datetime.timedelta(days=5)
        ).isoformat()
        self.assertEqual(data["estimated_delivery_date"], expected)

    def test_loads_without_blocking_render(self):
        html = self._visit(_order())
        tag = re.search(r'<script src="https://apis\.google\.com[^>]*>', html).group(0)
        self.assertIn("async", tag)
        self.assertIn("defer", tag)

    def test_no_snippet_without_email(self):
        html = self._visit(_order(email=""))
        self.assertNotIn(SNIPPET, html)
        self.assertNotIn("gcr-optin-data", html)

    def test_no_snippet_without_an_order_in_session(self):
        html = self.client.get("/success/").content.decode()
        self.assertNotIn(SNIPPET, html)

    def test_shown_once(self):
        order = _order()
        self.assertIn(SNIPPET, self._visit(order))
        self.assertNotIn(SNIPPET, self.client.get("/success/").content.decode())

    def test_unpaid_card_order_waits_for_the_payment(self):
        order = _order(
            payment_type=Order.PAYMENT_LIQPAY, status=Order.STATUS_AWAITING_PAYMENT
        )
        self.assertNotIn(SNIPPET, self._visit(order))
        self.assertEqual(self.client.session.get(SESSION_KEY), order.pk)
        Order.objects.filter(pk=order.pk).update(status=Order.STATUS_PAID)
        self.assertIn(SNIPPET, self.client.get("/success/").content.decode())

    def test_cancelled_order_gets_nothing(self):
        self.assertNotIn(SNIPPET, self._visit(_order(status=Order.STATUS_CANCELLED)))

    def test_email_cannot_break_out_of_the_script(self):
        order = _order()
        Order.objects.filter(pk=order.pk).update(email="a</script><b>@example.com")
        html = self._visit(order)
        self.assertNotIn("a</script><b>", html)

    def test_order_id_is_never_taken_from_the_url(self):
        order = _order()
        html = self.client.get(f"/success/?order={order.pk}").content.decode()
        self.assertNotIn(SNIPPET, html)


class CheckoutRemembersOrderTests(TestCase):
    def test_new_order_is_put_in_the_session(self):
        response = self.client.post(
            "/api/create-order/",
            {
                "name": "Оксана Петренко",
                "email": "buyer@example.com",
                "phone": "+380961112233",
                "city": "Київ",
                "address": "Відділення №1",
                "payment_type": Order.PAYMENT_CASH,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get()
        self.assertEqual(self.client.session.get(SESSION_KEY), order.pk)
