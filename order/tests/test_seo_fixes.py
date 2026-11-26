"""Checkout email is optional (audit 26.11.2026), except with a promocode."""

from unittest import mock

from django.test import TestCase

from catalog.models import PromoCode
from order.models import Order

URL = "/api/create-order/"


def _payload(**extra):
    data = {
        "name": "Олена Коваль",
        "phone": "+380961112233",
        "city": "Тернопіль",
        "address": "Відділення 1",
        "payment_method": "cash",
    }
    data.update(extra)
    return data


class OptionalCheckoutEmailTests(TestCase):
    def post(self, **extra):
        return self.client.post(URL, _payload(**extra), content_type="application/json")

    def test_order_without_email_is_created(self):
        resp = self.post()
        self.assertEqual(resp.status_code, 201, resp.content)
        order = Order.objects.get()
        self.assertEqual(order.email, "")
        self.assertEqual(order.status, Order.STATUS_NEW)

    def test_blank_email_is_created(self):
        resp = self.post(email="  ")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Order.objects.get().email, "")

    def test_email_is_kept_when_given(self):
        resp = self.post(email="olena@example.com")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Order.objects.get().email, "olena@example.com")

    def test_placeholder_email_is_stored_as_none(self):
        resp = self.post(email="x1@temp.com")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Order.objects.get().email, "")

    def test_bad_email_is_still_rejected(self):
        resp = self.post(email="not-an-email")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_promocode_without_email_asks_for_email(self):
        PromoCode.objects.create(code="WELCOME5", discount=5, max_uses_per_user=1)
        resp = self.post(promocode="WELCOME5")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("email", resp.json())
        self.assertFalse(Order.objects.exists())

    def test_session_promocode_without_email_asks_for_email(self):
        PromoCode.objects.create(code="WELCOME5", discount=5, max_uses_per_user=1)
        session = self.client.session
        session["applied_promocode"] = "WELCOME5"
        session.save()
        resp = self.post()
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_promocode_with_email_works(self):
        PromoCode.objects.create(code="WELCOME5", discount=5, max_uses_per_user=1)
        resp = self.post(promocode="WELCOME5", email="olena@example.com")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Order.objects.get().promocode_code, "WELCOME5")

    def test_confirmation_email_skips_empty_address(self):
        from order.email_utils import send_order_confirmation_email

        order = Order.objects.create(
            name="Олена", surname="Коваль", email="", payment_type=Order.PAYMENT_CASH
        )
        with mock.patch("order.email_utils.send_smtp_mail") as send:
            self.assertFalse(send_order_confirmation_email(order))
        send.assert_not_called()
