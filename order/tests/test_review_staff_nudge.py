"""
Buyers without an email still get asked for a review, through staff.

There is no customer channel besides email in the code (no SMS, and a
Telegram bot cannot write first to a phone number). So a phone-only order
goes to the staff chat with the buyer's phone and a ready message to forward
in Viber or Telegram, and the order admin shows the same links.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from catalog.api.views import REVIEWS_PER_IP_PER_HOUR
from catalog.models import ProductReview
from order.models import Order
from order.review_request import (
    STAFF_NUDGE_MAX_AGE_DAYS,
    ask_staff_due,
    ask_staff_for,
    build_staff_nudge,
    due_orders,
    due_orders_without_email,
    make_token,
)
from order.tests.test_review_request import OrderFixtureMixin

NOTIFY = "social.services.comment_notify.notify_staff_text"


class NoEmailSelectionTests(OrderFixtureMixin, TestCase):
    def test_phone_only_order_goes_to_staff_route(self):
        order = self._order(email="")
        self.assertIn(order, list(due_orders_without_email()))
        self.assertNotIn(order, list(due_orders()))

    def test_placeholder_email_goes_to_staff_route(self):
        """A @temp.com address reaches nobody; it used to come due daily."""
        order = self._order(email="x123@temp.com")
        self.assertNotIn(order, list(due_orders()))
        self.assertIn(order, list(due_orders_without_email()))

    def test_order_with_email_stays_on_the_letter_route(self):
        order = self._order()
        self.assertNotIn(order, list(due_orders_without_email()))

    def test_fresh_order_waits(self):
        order = self._order(email="", age_days=1)
        self.assertNotIn(order, list(due_orders_without_email()))

    def test_old_backlog_does_not_flood_the_chat(self):
        order = self._order(email="", age_days=STAFF_NUDGE_MAX_AGE_DAYS + 5)
        self.assertNotIn(order, list(due_orders_without_email()))


class StaffNudgeTests(OrderFixtureMixin, TestCase):
    def _phone_order(self, **kw):
        order = self._order(email="", **kw)
        Order.objects.filter(pk=order.pk).update(phone="+380961112233")
        order.refresh_from_db()
        return order

    def test_message_has_phone_and_working_link(self):
        order = self._phone_order()
        text = build_staff_nudge(order)
        self.assertIn("+380961112233", text)
        self.assertIn(self.product.slug, text)
        self.assertIn(f"?review={make_token(order)}", text)
        self.assertIn("Viber", text)

    def test_customer_text_has_no_long_dashes_and_is_not_escaped(self):
        order = self._phone_order()
        self.product.title = "Килим м'який"
        self.product.save(update_fields=["title"])
        text = build_staff_nudge(order)
        self.assertNotIn("—", text)
        self.assertNotIn("–", text)
        self.assertIn("Килим м'який", text)
        self.assertNotIn("&#x27;", text)

    def test_sent_once_and_marked_when_chat_accepts(self):
        order = self._phone_order()
        with patch(NOTIFY, return_value={"ok": True}) as notify:
            self.assertEqual(ask_staff_due(), 1)
            self.assertEqual(ask_staff_due(), 0)
        self.assertEqual(notify.call_count, 1)
        order.refresh_from_db()
        self.assertIsNotNone(order.review_request_sent_at)

    def test_failed_chat_send_is_retried_later(self):
        """The buyer is not contacted by this step, so a retry costs nothing."""
        order = self._phone_order()
        with patch(NOTIFY, return_value={"ok": False}):
            self.assertFalse(ask_staff_for(order))
        order.refresh_from_db()
        self.assertIsNone(order.review_request_sent_at)
        self.assertIn(order, list(due_orders_without_email()))

    def test_no_phone_no_email_is_dropped_quietly(self):
        order = self._order(email="")
        with patch(NOTIFY) as notify:
            self.assertFalse(ask_staff_for(order))
        notify.assert_not_called()
        order.refresh_from_db()
        self.assertIsNotNone(order.review_request_sent_at)

    def test_command_runs_both_routes(self):
        from io import StringIO

        from django.core.management import call_command

        self._phone_order()
        out = StringIO()
        with patch(NOTIFY, return_value={"ok": True}):
            call_command("send_review_requests", stdout=out)
        self.assertIn("Передано персоналу: 1", out.getvalue())

    def test_dry_run_sends_nothing(self):
        from io import StringIO

        from django.core.management import call_command

        order = self._phone_order()
        out = StringIO()
        with patch(NOTIFY) as notify:
            call_command("send_review_requests", "--dry-run", stdout=out)
        notify.assert_not_called()
        self.assertIn("+380961112233", out.getvalue())
        order.refresh_from_db()
        self.assertIsNone(order.review_request_sent_at)


class AdminReviewLinkTests(OrderFixtureMixin, TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            email="boss@example.com", password="x-test-pass-1"
        )
        self.client.force_login(user)

    def test_completed_order_shows_copyable_link(self):
        order = self._order(email="")
        html = self.client.get(
            f"/admin/order/order/{order.pk}/change/"
        ).content.decode()
        self.assertIn("Посилання для відгуку", html)
        self.assertIn(f"?review={make_token(order)}", html)

    def test_new_order_has_no_link_yet(self):
        order = self._order(status=Order.STATUS_NEW)
        html = self.client.get(
            f"/admin/order/order/{order.pk}/change/"
        ).content.decode()
        self.assertNotIn("?review=", html)


class TokenSkipsRateLimitTests(OrderFixtureMixin, TestCase):
    def test_buyer_with_invitation_is_never_held(self):
        """One order can hold several rugs, and the buyer reviews them all."""
        order = self._order()
        attr = order.cart.cart_products.first().product_attr
        ip = "203.0.113.50"
        for _ in range(REVIEWS_PER_IP_PER_HOUR):
            ProductReview.objects.create(
                product=self.product, name="Х", rating=5, content="тест тест тест",
                ip_address=ip,
            )
        response = self.client.post(
            "/api/product-reviews/",
            {
                "product": attr.id,
                "name": "Оксана",
                "rating": 5,
                "content": "Килим чудовий, ворс мʼякий",
                "review_token": make_token(order),
            },
            content_type="application/json",
            REMOTE_ADDR=ip,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.json()["published"], True)
