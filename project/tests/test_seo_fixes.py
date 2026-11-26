"""Audit 26.11.2026: AI photos out of JSON-LD, the store as LocalBusiness,
/profile/ for guests, versioned thumbnails."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from project.seo_jsonld import _image_urls, organization_graph

SITE = "https://mrcarpet24.com"


def _img(name, is_ai=False):
    return SimpleNamespace(
        image=SimpleNamespace(url=f"/media/{name}", name=name), is_ai=is_ai
    )


@override_settings(SITE_URL=SITE)
class JsonLdImageTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")
        self.product = SimpleNamespace(
            image=SimpleNamespace(url="/media/products/main.webp", name="products/main.webp")
        )

    def test_ai_interior_photos_are_skipped(self):
        urls = _image_urls(
            self.request,
            self.product,
            [_img("products/additional/real.webp"), _img("products/additional/room.webp", is_ai=True)],
        )
        self.assertEqual(
            urls,
            [
                f"{SITE}/media/products/main.webp",
                f"{SITE}/media/products/additional/real.webp",
            ],
        )

    def test_images_without_flag_are_kept(self):
        img = SimpleNamespace(image=SimpleNamespace(url="/media/x.webp", name="x.webp"))
        urls = _image_urls(self.request, self.product, [img])
        self.assertIn(f"{SITE}/media/x.webp", urls)


@override_settings(SITE_URL=SITE)
class LocalBusinessTests(SimpleTestCase):
    def test_organization_is_a_home_goods_store_with_address(self):
        org = organization_graph(RequestFactory().get("/"))
        self.assertEqual(org["@type"], ["Organization", "HomeGoodsStore"])
        self.assertEqual(org["@id"], f"{SITE}/#organization")
        self.assertEqual(org["url"], f"{SITE}/")
        self.assertEqual(org["telephone"], "+380963988875")
        self.assertEqual(org["address"]["streetAddress"], "вул. Незалежності 5а")
        self.assertEqual(org["address"]["addressLocality"], "Ланівці")
        self.assertTrue(org["image"].endswith("mr-carpet-logo.png"))
        # Nothing the site does not state: no invented hours or coordinates.
        for key in ("openingHours", "openingHoursSpecification", "geo", "priceRange"):
            self.assertNotIn(key, org)


class ProfileLoginRedirectTests(TestCase):
    def test_guest_profile_goes_home_not_to_a_404(self):
        resp = self.client.get("/profile/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/?next=/profile/")
        self.assertEqual(self.client.get("/").status_code, 200)


class ThumbnailVersionTests(SimpleTestCase):
    def test_thumbs_live_under_a_versioned_dir(self):
        from catalog import thumbnails

        name = thumbnails._thumb_name("products/a.jpg", 400)
        self.assertEqual(name, f"thumbs/v{thumbnails.THUMBS_VERSION}/w400/products/a.webp")
        # The deploy chmods /app/media/thumbs recursively; stay under it.
        self.assertTrue(name.startswith("thumbs/"))
        self.assertEqual(thumbnails.DEFAULT_QUALITY, 72)
        self.assertEqual(thumbnails.WEBP_METHOD, 6)
