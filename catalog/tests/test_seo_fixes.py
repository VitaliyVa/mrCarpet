"""Audit 26.11.2026: a page that does not exist is a 404, and listings offer
a real product photo for og:image instead of the logo."""

from django.test import TestCase, override_settings

from catalog.models import Product, ProductAttribute, ProductCategory, Size

SITE = "https://mrcarpet24.com"
SIZE_PATH = "/catalog/rozmir/160x230/"


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
class StrictPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = ProductCategory.objects.create(title="Турецькі", slug="turetski")
        size = Size.objects.create(title="1.6x2.3")
        # 13 buyable products -> 2 pages of 12
        for i in range(13):
            p = Product.objects.create(
                title=f"Килим {i}", slug=f"kylym-fix-{i}", image=f"products/rug-{i}.jpg"
            )
            ProductAttribute.objects.create(product=p, size=size, price=1000 + i, quantity=3)
            p.categories.add(cls.cat)
        cls.paths = (
            cls.cat.get_absolute_url(),
            "/catalog/collection/",
            SIZE_PATH,
        )

    def test_real_pages_stay_200(self):
        for path in self.paths:
            for qs in ("", "?page=1", "?page=2", "?page="):
                resp = self.client.get(path + qs)
                self.assertEqual(resp.status_code, 200, path + qs)

    def test_missing_pages_are_404(self):
        for path in self.paths + ("/catalog/stock/",):
            for qs in ("?page=999", "?page=3", "?page=0", "?page=-1", "?page=abc", "?page=2.0"):
                resp = self.client.get(path + qs)
                self.assertEqual(resp.status_code, 404, path + qs)

    def test_empty_stock_first_page_is_still_200(self):
        self.assertEqual(self.client.get("/catalog/stock/").status_code, 200)
        self.assertEqual(self.client.get("/catalog/stock/?page=1").status_code, 200)

    def test_page_one_canonical_is_clean(self):
        resp = self.client.get(self.cat.get_absolute_url() + "?page=1")
        self.assertIn(
            f'<link rel="canonical" href="{SITE}{self.cat.get_absolute_url()}"',
            resp.content.decode(),
        )

    def test_listings_offer_a_product_photo_for_og_image(self):
        for path in self.paths:
            resp = self.client.get(path)
            url = resp.context["og_image_url"]
            self.assertTrue(url and url.startswith(f"{SITE}/media/products/rug-"), (path, url))

    def test_category_picture_wins_over_products(self):
        self.cat.image = "categories/turetski.webp"
        ProductCategory.objects.filter(pk=self.cat.pk).update(image=self.cat.image)
        resp = self.client.get(self.cat.get_absolute_url())
        self.assertEqual(
            resp.context["og_image_url"], f"{SITE}/media/categories/turetski.webp"
        )

    def test_placeholder_photo_is_not_offered(self):
        Product.objects.order_by().update(image="products/default.png")
        resp = self.client.get("/catalog/collection/")
        self.assertIsNone(resp.context["og_image_url"])
