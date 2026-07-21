"""
The review invitation: one per order, links that open the form, and a token
that proves the purchase without asking the customer to prove anything.
"""

from django.test import RequestFactory, TestCase
from django.utils import timezone

from cart.models import Cart, CartProduct
from catalog.models import Product, ProductAttribute, ProductReview, Size
from order.models import Order
from order.review_request import (
    DELAY_DAYS,
    build_email,
    due_orders,
    make_token,
    products_in,
    read_token,
    review_url,
    send_for,
)


class OrderFixtureMixin:
    def _order(self, *, status=Order.STATUS_COMPLETED, email="buyer@example.com",
               age_days=DELAY_DAYS + 1):
        product = Product.objects.create(title="Килим тест", slug="kylym-invite")
        size = Size.objects.create(title="1.6 x 2.3")
        attr = ProductAttribute.objects.create(
            product=product, size=size, price=1000, quantity=3
        )
        order = Order.objects.create(name="Оксана", email=email, status=status)
        # Cart.order is the OneToOne side; `order.cart` is the reverse.
        cart = Cart.objects.create(order=order)
        CartProduct.objects.create(cart=cart, product_attr=attr, quantity=1)
        # The signal stamps completed_at on the transition; the test rewinds
        # it to stand in for an order finished `age_days` ago.
        Order.objects.filter(pk=order.pk).update(
            completed_at=(
                timezone.now() - timezone.timedelta(days=age_days)
                if status == Order.STATUS_COMPLETED
                else None
            )
        )
        order.refresh_from_db()
        self.product = product
        return order


class DueSelectionTests(OrderFixtureMixin, TestCase):
    def test_a_completed_order_past_the_delay_is_due(self):
        order = self._order()
        self.assertIn(order, list(due_orders()))

    def test_a_fresh_order_is_not_asked_yet(self):
        """Asking on delivery day asks someone who has not unrolled it."""
        order = self._order(age_days=1)
        self.assertNotIn(order, list(due_orders()))

    def test_an_unfinished_order_is_not_asked(self):
        order = self._order(status=Order.STATUS_PAID)
        self.assertNotIn(order, list(due_orders()))

    def test_an_order_without_an_email_is_skipped(self):
        order = self._order(email="")
        self.assertNotIn(order, list(due_orders()))

    def test_nobody_is_asked_twice(self):
        """The dedupe is a stored timestamp, not a date window, so a run after
        a week of downtime asks about the backlog once — not once per day."""
        order = self._order()
        send_for(order)
        self.assertNotIn(order, list(due_orders()))

    def test_the_order_is_marked_even_if_the_mail_fails(self):
        """Losing an invitation is cheaper than sending it twice; a shop that
        nags is worse than one that never asks."""
        from unittest.mock import patch

        order = self._order()
        with patch("project.smtp_utils.send_smtp_mail", side_effect=RuntimeError):
            try:
                send_for(order)
            except RuntimeError:
                pass
        order.refresh_from_db()
        self.assertIsNotNone(order.review_request_sent_at)


class CompletedStampTests(OrderFixtureMixin, TestCase):
    """
    The clock starts when the order is finished, not when it was last edited.
    """

    def test_transition_stamps_the_moment(self):
        order = Order.objects.create(name="Оксана", email="a@b.com")
        self.assertIsNone(order.completed_at)
        order.status = Order.STATUS_COMPLETED
        order.save()
        order.refresh_from_db()
        self.assertIsNotNone(order.completed_at)

    def test_editing_the_order_later_does_not_move_the_clock(self):
        """Correcting a phone number must not push the invitation away."""
        order = Order.objects.create(name="Оксана", email="a@b.com")
        order.status = Order.STATUS_COMPLETED
        order.save()
        order.refresh_from_db()
        stamped = order.completed_at

        order.name = "Оксана П."
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.completed_at, stamped)

    def test_bouncing_the_status_does_not_restart_it(self):
        """The customer received the rug the first time."""
        order = Order.objects.create(name="Оксана", email="a@b.com")
        order.status = Order.STATUS_COMPLETED
        order.save()
        order.refresh_from_db()
        stamped = order.completed_at

        order.status = Order.STATUS_SHIPPED
        order.save()
        order.status = Order.STATUS_COMPLETED
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.completed_at, stamped)


class TokenTests(OrderFixtureMixin, TestCase):
    def test_token_round_trips_to_the_order(self):
        order = self._order()
        self.assertEqual(read_token(make_token(order)), order)

    def test_a_forged_token_is_refused(self):
        self.assertIsNone(read_token("123:garbage"))
        self.assertIsNone(read_token(""))

    def test_link_points_at_the_product_and_opens_the_form(self):
        order = self._order()
        url = review_url(order, self.product)
        self.assertIn(self.product.slug, url)
        self.assertIn("?review=", url)


class EmailTests(OrderFixtureMixin, TestCase):
    def test_email_names_every_product_bought(self):
        order = self._order()
        subject, text, html = build_email(order)
        self.assertIn("Килим тест", html)
        self.assertIn("?review=", html)
        self.assertIn("Килим тест", text)

    def test_email_is_not_built_for_an_empty_order(self):
        order = self._order()
        order.cart.cart_products.all().delete()
        self.assertIsNone(build_email(order))

    def test_an_order_with_no_items_is_not_retried_forever(self):
        """Left unmarked it would come due again every day and log into the
        void; staff get told once instead."""
        order = self._order()
        order.cart.cart_products.all().delete()
        self.assertFalse(send_for(order))
        order.refresh_from_db()
        self.assertIsNotNone(order.review_request_sent_at)
        self.assertNotIn(order, list(due_orders()))

    def test_products_in_deduplicates(self):
        order = self._order()
        attr = order.cart.cart_products.first().product_attr
        CartProduct.objects.create(cart=order.cart, product_attr=attr, quantity=1)
        self.assertEqual(len(products_in(order)), 1)


class ModalOpeningTests(OrderFixtureMixin, TestCase):
    """The link has to land on an open form — a customer who has to hunt for
    it closes the tab."""

    def _context(self, query):
        from catalog.views import _review_invite_context

        return _review_invite_context(RequestFactory().get(f"/?{query}"))

    def test_no_param_leaves_the_page_alone(self):
        self.assertFalse(self._context("")["open_review_modal"])

    def test_plain_flag_opens_the_form(self):
        """A link anyone can paste anywhere."""
        self.assertTrue(self._context("review=1")["open_review_modal"])

    def test_token_opens_the_form_and_fills_it_in(self):
        order = self._order()
        context = self._context(f"review={make_token(order)}")
        self.assertTrue(context["open_review_modal"])
        self.assertEqual(context["review_name"], "Оксана")
        self.assertEqual(context["review_email"], "buyer@example.com")

    def test_an_expired_or_forged_token_still_opens_the_form(self):
        """Degrades to the plain case rather than to an error page: the
        visitor can still write a review, it just is not verified."""
        context = self._context("review=nonsense")
        self.assertTrue(context["open_review_modal"])
        self.assertEqual(context["review_name"], "")


class VerifiedPurchaseTests(OrderFixtureMixin, TestCase):
    def _submit(self, **extra):
        order = self._order()
        attr = order.cart.cart_products.first().product_attr
        payload = {
            "product": attr.id,
            "name": "Оксана",
            "rating": 5,
            "content": "Гарний",
        }
        payload.update(extra)
        self.client.post(
            "/api/product-reviews/", payload, content_type="application/json"
        )
        return order

    def test_token_earns_the_verified_badge(self):
        order = self._order()
        attr = order.cart.cart_products.first().product_attr
        self.client.post(
            "/api/product-reviews/",
            {
                "product": attr.id,
                "name": "Оксана",
                "rating": 5,
                "review_token": make_token(order),
            },
            content_type="application/json",
        )
        self.assertTrue(ProductReview.objects.get().verified_purchase)

    def test_a_token_for_another_product_does_not_verify_this_one(self):
        """Otherwise one invitation would verify a review of anything."""
        order = self._order()
        other = Product.objects.create(title="Інший", slug="inshyi")
        size = Size.objects.create(title="2 x 3")
        other_attr = ProductAttribute.objects.create(
            product=other, size=size, price=900, quantity=1
        )
        self.client.post(
            "/api/product-reviews/",
            {
                "product": other_attr.id,
                "name": "Оксана",
                "rating": 5,
                "review_token": make_token(order),
            },
            content_type="application/json",
        )
        self.assertFalse(ProductReview.objects.get().verified_purchase)

    def test_no_token_means_no_badge(self):
        self._submit()
        self.assertFalse(ProductReview.objects.get().verified_purchase)
