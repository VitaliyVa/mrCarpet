"""
Anyone can open the review form from the product page; moderation stays.

The form used to need an account: a guest saw "please log in or register" and
no button, and once a product had a review the button was gone for everyone
(it sat in an HTML comment). The API has always taken anonymous posts and
holds them for a human, so the gate only cost reviews.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from catalog.api.views import REVIEWS_PER_IP_PER_HOUR
from catalog.models import Product, ProductAttribute, ProductReview, Size

BUTTON = 'data-href="review-write-modal"'


class ReviewAccessMixin:
    def setUp(self):
        self.product = Product.objects.create(title="Килим тест", slug="kylym-access")
        size = Size.objects.create(title="1.6 x 2.3")
        self.attr = ProductAttribute.objects.create(
            product=self.product, size=size, price=1000, quantity=5
        )

    def _html(self):
        return self.client.get(self.product.get_absolute_url()).content.decode()

    def _post(self, ip="203.0.113.7", **overrides):
        payload = {
            "product": self.attr.id,
            "name": "Оксана",
            "rating": 5,
            "content": "Гарний килим, дуже мʼякий",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/product-reviews/",
            payload,
            content_type="application/json",
            REMOTE_ADDR=ip,
        )


class ReviewButtonTests(ReviewAccessMixin, TestCase):
    def test_guest_sees_the_button_when_there_are_no_reviews(self):
        html = self._html()
        self.assertIn(BUTTON, html)
        self.assertIn("ще немає відгуків", html)
        self.assertNotIn("авторизуйтеся", html)

    def test_button_stays_once_the_product_has_reviews(self):
        ProductReview.objects.create(
            product=self.product, name="Марія", rating=5, content="Гарний килим",
            status=ProductReview.Status.APPROVED,
        )
        html = self._html()
        self.assertIn(BUTTON, html)
        self.assertNotIn("ще немає відгуків", html)
        # Not left over in an HTML comment: the live button is the only copy.
        self.assertEqual(html.count(BUTTON), 1)
        self.assertNotIn("<!-- <div class=\"product_reviews__add-review\">", html)

    def test_signed_in_buyer_sees_the_same_button(self):
        user = get_user_model().objects.create_user(
            email="buyer@example.com", password="x-test-pass-1"
        )
        self.client.force_login(user)
        self.assertIn(BUTTON, self._html())

    def test_the_form_itself_is_on_the_page_for_guests(self):
        html = self._html()
        self.assertIn("review-write-modal__send-review-btn", html)


class ModerationStaysTests(ReviewAccessMixin, TestCase):
    def test_guest_review_waits_and_says_so(self):
        response = self._post()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIs(body["published"], False)
        self.assertIn("після перевірки", body["message"])
        self.assertEqual(
            ProductReview.objects.get().status, ProductReview.Status.PENDING
        )

    def test_waiting_review_is_not_on_the_page(self):
        self._post(content="Спам спам спам спам")
        self.assertNotIn("Спам спам", self._html())


class RateLimitTests(ReviewAccessMixin, TestCase):
    def test_one_address_is_held_after_its_hourly_share(self):
        for _ in range(REVIEWS_PER_IP_PER_HOUR):
            self.assertEqual(self._post().status_code, 201)
        blocked = self._post()
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("пізніше", blocked.json()["message"])
        self.assertEqual(ProductReview.objects.count(), REVIEWS_PER_IP_PER_HOUR)

    def test_other_addresses_are_not_affected(self):
        for _ in range(REVIEWS_PER_IP_PER_HOUR):
            self._post()
        self.assertEqual(self._post(ip="198.51.100.9").status_code, 201)

    def test_old_reviews_do_not_count(self):
        from django.utils import timezone

        for _ in range(REVIEWS_PER_IP_PER_HOUR):
            self._post()
        ProductReview.objects.update(
            created=timezone.now() - timezone.timedelta(hours=2)
        )
        self.assertEqual(self._post().status_code, 201)

    def test_staff_is_never_held(self):
        user = get_user_model().objects.create_user(
            email="a@example.com", password="x-test-pass-1",
            is_staff=True,
        )
        self.client.force_login(user)
        for _ in range(REVIEWS_PER_IP_PER_HOUR + 1):
            self.assertEqual(self._post().status_code, 201)

    def test_junk_forwarded_header_does_not_break_the_form(self):
        response = self.client.post(
            "/api/product-reviews/",
            {
                "product": self.attr.id,
                "name": "Оксана",
                "rating": 5,
                "content": "Гарний килим, дуже мʼякий",
            },
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="not-an-ip, 10.0.0.1",
            REMOTE_ADDR="192.0.2.44",
        )
        self.assertEqual(response.status_code, 201)
        # Falls back to the socket address, so junk cannot dodge the limit.
        self.assertEqual(ProductReview.objects.get().ip_address, "192.0.2.44")
