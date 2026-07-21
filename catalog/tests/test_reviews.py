"""
Reviews are public to write and moderated to publish.

The create endpoint has always accepted anonymous POSTs — IsAdminEdit only
implements has_object_permission, which DRF does not call on create. That is
acceptable for a review form and was not acceptable downstream: every review
went straight into the aggregateRating Google reads, so a stranger could set
the star rating of any product. Verified live before this was fixed: an
anonymous POST returned 201.

These tests pin the two halves that make it safe — nothing is published
without a human, and nothing unpublished reaches the structured data.
"""

from django.test import RequestFactory, TestCase

from catalog.models import Product, ProductAttribute, ProductReview, Size


class ReviewFactoryMixin:
    def _product(self):
        product = Product.objects.create(title="Килим тест", slug="kylym-review")
        size = Size.objects.create(title="1.6 x 2.3")
        self.attr = ProductAttribute.objects.create(
            product=product, size=size, price=1000, quantity=5
        )
        return product

    def _post(self, **overrides):
        payload = {
            "product": self.attr.id,
            "name": "Оксана",
            "rating": 5,
            "content": "Гарний килим",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/product-reviews/", payload, content_type="application/json"
        )


class SubmissionTests(ReviewFactoryMixin, TestCase):
    def setUp(self):
        self.product = self._product()

    def test_anonymous_can_submit(self):
        """The form is for customers; requiring an account would empty it."""
        response = self._post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProductReview.objects.count(), 1)

    def test_submission_is_not_published(self):
        self._post()
        self.assertEqual(
            ProductReview.objects.get().status, ProductReview.Status.PENDING
        )

    def test_submitter_cannot_publish_their_own_review(self):
        """The obvious attack: send status=approved and skip moderation."""
        self._post(status="approved")
        self.assertEqual(
            ProductReview.objects.get().status, ProductReview.Status.PENDING
        )

    def test_submitter_cannot_claim_a_verified_purchase(self):
        self._post(verified_purchase=True)
        self.assertFalse(ProductReview.objects.get().verified_purchase)

    def test_response_does_not_echo_the_stored_row(self):
        """It would leak the moderation state and the email of a review that
        is not public."""
        response = self._post(email="buyer@example.com")
        self.assertNotIn("status", response.json())
        self.assertNotIn("email", response.json())

    def test_listing_hides_unapproved_reviews(self):
        self._post()
        listed = self.client.get("/api/product-reviews/").json()
        rows = listed.get("results", listed)
        self.assertEqual(len(rows), 0)

    def test_listing_shows_approved_ones(self):
        self._post()
        ProductReview.objects.update(status=ProductReview.Status.APPROVED)
        listed = self.client.get("/api/product-reviews/").json()
        rows = listed.get("results", listed)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("email", rows[0])


class StructuredDataTests(ReviewFactoryMixin, TestCase):
    """
    The half that actually protects the search listing.

    Moderation is decorative if the JSON-LD keeps reading every row.
    """

    def setUp(self):
        self.product = self._product()

    def _rating(self):
        from project.seo_jsonld import product_graph

        request = RequestFactory().get("/", HTTP_HOST="mrcarpet24.com")
        data = product_graph(request, self.product) or {}
        return data.get("aggregateRating")

    def test_pending_review_stays_out_of_the_rating(self):
        ProductReview.objects.create(
            product=self.product, name="Спам", rating=1, content="."
        )
        self.assertIsNone(self._rating())

    def test_rejected_review_stays_out_of_the_rating(self):
        ProductReview.objects.create(
            product=self.product,
            name="Спам",
            rating=1,
            status=ProductReview.Status.REJECTED,
        )
        self.assertIsNone(self._rating())

    def test_approved_reviews_are_averaged(self):
        for value in (5, 4):
            ProductReview.objects.create(
                product=self.product,
                name="Клієнт",
                rating=value,
                status=ProductReview.Status.APPROVED,
            )
        rating = self._rating()
        self.assertEqual(rating["ratingValue"], 4.5)
        self.assertEqual(rating["reviewCount"], 2)

    def test_one_bad_approved_review_still_counts(self):
        """Moderation is for spam, not for hiding criticism — a shop showing
        only five stars is the pattern Google penalises."""
        ProductReview.objects.create(
            product=self.product,
            name="Клієнт",
            rating=2,
            status=ProductReview.Status.APPROVED,
        )
        self.assertEqual(self._rating()["ratingValue"], 2)
