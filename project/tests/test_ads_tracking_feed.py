"""GA4 item_id = Merchant feed g:id, feed main image size, checkout form and cart labels."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase as PlainTestCase

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from cart.models import Cart, CartProduct
from project import merchant_feed
from project.ga4_ecommerce import cart_ecommerce_payload
from project.merchant_feed import build_items, feed_products, offer_id
from project.tests.test_merchant_feed import _make_product

ROOT = Path(settings.BASE_DIR)
NODE = shutil.which("node")
BUNDLES = ROOT / "static" / "source" / "pages"


def _json_script(html: str, element_id: str):
    m = re.search(
        rf'<script id="{element_id}" type="application/json">(.*?)</script>', html, re.S
    )
    return json.loads(m.group(1)) if m else None


class OfferIdTests(PlainTestCase):
    def test_fixed_priced_size_gets_product_and_attr_pk(self):
        attr = SimpleNamespace(pk=300, price=1200, custom_attribute=False)
        self.assertEqual(offer_id(SimpleNamespace(pk=44), attr), "44-300")
        self.assertEqual(offer_id(44, attr), "44-300")

    def test_sizes_not_in_feed_keep_bare_pk(self):
        product = SimpleNamespace(pk=44)
        self.assertEqual(offer_id(product), "44")
        self.assertEqual(offer_id(product, None), "44")
        custom = SimpleNamespace(pk=7, price=None, custom_attribute=True, custom_price=500)
        self.assertEqual(offer_id(product, custom), "44")
        unpriced = SimpleNamespace(pk=8, price=0, custom_attribute=False)
        self.assertEqual(offer_id(product, unpriced), "44")


@override_settings(GA4_MEASUREMENT_ID="G-TEST", GTM_CONTAINER_ID="")
class ItemIdMatchesFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _make_product(cls)
        cls.custom = cls.product.product_attr.get(custom_attribute=True)

    def _feed_ids(self):
        return {item["link"].rsplit("=", 1)[1]: item["id"] for item in build_items(feed_products())}

    def _pdp(self, query=""):
        resp = self.client.get(f"{self.product.get_absolute_url()}{query}", secure=True)
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_view_item_id_equals_feed_id_for_same_size(self):
        feed = self._feed_ids()
        for attr in (self.small, self.big):
            item = _json_script(self._pdp(f"?size={attr.pk}"), "ga4-view-item")
            self.assertEqual(item["item_id"], feed[str(attr.pk)])
            self.assertEqual(item["item_group_id"], str(self.product.pk))

    def test_bare_url_uses_default_in_stock_size(self):
        item = _json_script(self._pdp(), "ga4-view-item")
        self.assertEqual(item["item_id"], f"{self.product.pk}-{self.small.pk}")

    def test_size_chips_carry_feed_id(self):
        html = self._pdp()
        feed = self._feed_ids()
        for attr in (self.small, self.big):
            self.assertRegex(
                html,
                rf'data-item="{attr.pk}"\s+data-ga-item-id="{re.escape(feed[str(attr.pk)])}"',
            )

    def _cart(self, *lines):
        cart = Cart.objects.create()
        for attr, extra in lines:
            CartProduct.objects.create(cart=cart, product_attr=attr, quantity=1, **extra)
        session = self.client.session
        session["cart_id"] = cart.id
        session.save()
        return cart

    def test_cart_and_purchase_lines_use_feed_id(self):
        cart = self._cart((self.big, {}))
        feed = self._feed_ids()
        items = cart_ecommerce_payload(cart)["items"]
        self.assertEqual(items[0]["item_id"], feed[str(self.big.pk)])
        self.assertEqual(items[0]["item_group_id"], str(self.product.pk))

        html = self.client.get("/cart/").content.decode()
        self.assertEqual(_json_script(html, "ga4-cart-data")["items"][0]["item_id"], feed[str(self.big.pk)])
        self.assertIn(f'data-ga-item-id="{feed[str(self.big.pk)]}"', html)

    def test_cut_to_length_line_keeps_bare_pk(self):
        cart = self._cart((self.custom, {"length": 2, "total_price": 2000}))
        item = cart_ecommerce_payload(cart)["items"][0]
        self.assertEqual(item["item_id"], str(self.product.pk))

    def test_blog_card_carries_feed_id_of_priced_size(self):
        from blog.services.product_cards import build_card, render_block

        card = build_card(self.product)
        self.assertEqual(card["ga_item_id"], f"{self.product.pk}-{self.small.pk}")
        self.assertIn(f'data-ga-item-id="{card["ga_item_id"]}"', render_block([self.product.slug]))


class _MediaMixin:
    """Real image files in a throwaway MEDIA_ROOT, so widths can be read."""

    def setUp(self):
        super().setUp()
        self._media = tempfile.mkdtemp()
        self._override = override_settings(MEDIA_ROOT=self._media)
        self._override.enable()
        merchant_feed._IMAGE_WIDTHS.clear()

    def tearDown(self):
        self._override.disable()
        merchant_feed._IMAGE_WIDTHS.clear()
        shutil.rmtree(self._media, ignore_errors=True)
        super().tearDown()

    def _png(self, name: str, width: int, height: int) -> str:
        from PIL import Image

        path = Path(self._media) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (width, height), "white").save(path, "PNG")
        return name


class FeedMainImageTests(_MediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        _make_product(self)
        from catalog.models import ProductImage

        self.ProductImage = ProductImage
        self.product.image = self._png("products/card.png", 500, 750)
        self.product.save()

    def _gallery(self, name, width, height, sort_order, is_ai=False):
        return self.ProductImage.objects.create(
            product=self.product,
            image=self._png(f"products/additional/{name}", width, height),
            sort_order=sort_order,
            is_ai=is_ai,
        )

    def _images(self):
        item = build_items(feed_products())[0]
        return item["image_link"], item["additional_image_link"]

    def test_small_card_swapped_for_first_large_gallery_photo(self):
        self._gallery("close.png", 600, 600, 10)
        self._gallery("big.png", 960, 1280, 20)
        self._gallery("big2.png", 1024, 768, 30)
        main, extra = self._images()
        self.assertTrue(main.endswith("/products/additional/big.png"), main)
        self.assertTrue(extra[0].endswith("/products/card.png"), extra)
        self.assertEqual(len(extra), 3)
        self.assertEqual(len(set([main, *extra])), 4)

    def test_large_card_image_stays_main(self):
        self.product.image = self._png("products/card_big.png", 1200, 1600)
        self.product.save()
        self._gallery("big.png", 960, 1280, 10)
        main, extra = self._images()
        self.assertTrue(main.endswith("/products/card_big.png"), main)
        self.assertTrue(extra[0].endswith("/products/additional/big.png"))

    def test_no_large_gallery_photo_keeps_card(self):
        self._gallery("small.png", 640, 640, 10)
        main, extra = self._images()
        self.assertTrue(main.endswith("/products/card.png"), main)
        self.assertEqual(len(extra), 1)

    def test_ai_interiors_never_reach_the_feed(self):
        self._gallery("room.png", 1536, 1024, 5, is_ai=True)
        self._gallery("big.png", 960, 1280, 10)
        main, extra = self._images()
        self.assertTrue(main.endswith("/products/additional/big.png"), main)
        self.assertFalse(any("room.png" in url for url in [main, *extra]))

    def test_unreadable_files_keep_old_order(self):
        self.product.image = "products/missing.webp"
        self.product.save()
        self.ProductImage.objects.create(
            product=self.product, image="products/additional/missing2.webp", sort_order=10
        )
        main, extra = self._images()
        self.assertTrue(main.endswith("/products/missing.webp"), main)
        self.assertTrue(extra[0].endswith("/products/additional/missing2.webp"))


class CheckoutFormAndLabelsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _make_product(cls)

    def _with_cart(self):
        cart = Cart.objects.create()
        CartProduct.objects.create(cart=cart, product_attr=self.small, quantity=1)
        session = self.client.session
        session["cart_id"] = cart.id
        session.save()

    @staticmethod
    def _input(html, element_id):
        m = re.search(rf'<input\s[^>]*id="{element_id}"[^>]*>', html, re.S)
        assert m, element_id
        return m.group(0)

    def test_checkout_inputs_have_mobile_keyboards_and_autofill(self):
        self._with_cart()
        html = self.client.get("/checkout/").content.decode()
        phone = self._input(html, "nova-post-phone")
        for attr in ('type="tel"', 'inputmode="tel"', 'autocomplete="tel"', 'name="phone"'):
            self.assertIn(attr, phone)
        name = self._input(html, "nova-post-name")
        self.assertIn('autocomplete="name"', name)
        self.assertIn("placeholder=\"Ім'я та прізвище отримувача\"", name)
        email = self._input(html, "nova-post-email")
        self.assertIn('autocomplete="email"', email)
        self.assertIn('type="email"', email)

    def test_checkout_submit_says_confirm(self):
        self._with_cart()
        html = self.client.get("/checkout/").content.decode()
        btn = re.search(r'<button class="basket__to-order-btn[^>]*>(.*?)</button>', html, re.S)
        self.assertEqual(btn.group(1).strip(), "Підтвердити замовлення")
        self.assertNotIn("Перейти до оформлення", html)

    def test_checkout_shows_order_summary_and_comment_field(self):
        self._with_cart()
        html = self.client.get("/checkout/").content.decode()
        self.assertIn("<h1>Оформлення замовлення</h1>", html)
        self.assertIn('class="basket__summary basket_right"', html)
        self.assertEqual(html.count('class="basket__summary-item"'), 1)
        self.assertIn(self.product.title, html)
        textarea = re.search(r'<textarea[^>]*id="order-comment"[^>]*>', html, re.S)
        self.assertIsNotNone(textarea)
        self.assertIn('maxlength="1000"', textarea.group(0))
        self.assertNotIn("required", textarea.group(0))
        self.assertIn('<span id="cart-count">1 товар</span>', html)
        self.assertIn('<span id="cart-count">1 товар</span>', self.client.get("/cart/").content.decode())

    def test_checkout_bundle_sends_the_comment(self):
        from pathlib import Path

        from django.conf import settings

        bundle = Path(settings.BASE_DIR, "static/source/pages/basket/index.js").read_text(encoding="utf-8")
        self.assertIn("order-comment", bundle)

    def test_cart_button_says_place_order(self):
        self._with_cart()
        html = self.client.get("/cart/").content.decode()
        self.assertIn('class="btn-gold">Оформити замовлення</a>', html)
        self.assertNotIn("Замовлення підтверджую", html)

    def test_pdp_add_to_cart_label(self):
        html = self.client.get(self.product.get_absolute_url(), secure=True).content.decode()
        btn = re.search(r'<button\s+type="button"\s+class="add-to-cart btn-gold"[^>]*>(.*?)</button>', html, re.S)
        self.assertEqual(btn.group(1).strip(), "Додати в кошик")
        self.assertNotIn("Добавити", html)


class BundleSyncTests(SimpleTestCase):
    """Production serves the compiled bundles (webpack does not run on deploy)."""

    def _bundles(self, marker):
        found = [p for p in BUNDLES.glob("*/index.js") if marker in p.read_text(encoding="utf-8")]
        self.assertTrue(found, marker)
        return found

    def test_item_id_from_size_chip_in_every_bundle(self):
        for bundle in self._bundles("gaListName||"):
            text = bundle.read_text(encoding="utf-8")
            self.assertIn("dataset.gaItemId", text, bundle)
            self.assertIn("item_group_id:String(", text, bundle)

    def test_add_to_cart_toast_links_to_checkout_in_every_bundle(self):
        for bundle in self._bundles("Товар додано в кошик"):
            text = bundle.read_text(encoding="utf-8")
            self.assertIn('class="checkout-notification__action">Оформити замовлення</a>', text, bundle)
            self.assertIn(".checkout-notification__action\"", text, bundle)  # cta_click
            css = bundle.with_suffix(".css").read_text(encoding="utf-8")
            self.assertIn(".checkout-notification__action{", css, bundle)

    def test_cut_to_length_add_to_cart_sends_bare_pk(self):
        src = (ROOT / "static/development/components/pages/product/product.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("analyticsItem.item_id = analyticsItem.item_group_id", src)
        bundle = (BUNDLES / "product" / "index.js").read_text(encoding="utf-8")
        self.assertRegex(bundle, r"(\w)\.item_group_id&&\(\1\.item_id=\1\.item_group_id\)")

    def test_sources_match(self):
        basket = (ROOT / "static/development/api/basket.js").read_text(encoding="utf-8")
        self.assertIn("withCheckoutLink(data?.message", basket)
        scss = (ROOT / "static/development/components/pages/basket/notification.scss").read_text(
            encoding="utf-8"
        )
        self.assertIn("&__action", scss)
        form = (ROOT / "static/development/components/pages/basket/order-form.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("введіть ім'я та прізвище", form)


class ItemFromProductElNodeTests(SimpleTestCase):
    """Runs static/development/utils/analytics.js under node with a stub DOM."""

    def setUp(self):
        if not NODE:
            self.skipTest("node not installed")

    def test_item_id_prefers_explicit_then_chip_then_product(self):
        script = """
globalThis.window = globalThis;
globalThis.document = { readyState: "complete", addEventListener() {}, querySelectorAll() { return []; } };
const { itemFromProductEl } = await import(%s);
const el = (data, chip) => ({
  dataset: data,
  querySelector: (sel) => (sel === ".size-label.active" ? chip : null),
  closest: () => null,
});
const chip = { dataset: { gaItemId: "44-300", size: "2.0x3.0" }, textContent: "2.0x3.0" };
console.log(JSON.stringify([
  itemFromProductEl(el({ catalogProductId: "44", productId: "300" }, chip)),
  itemFromProductEl(el({ catalogProductId: "44", productId: "301" }, null)),
  itemFromProductEl(el({ catalogProductId: "44", gaItemId: "44-9" }, chip)),
  itemFromProductEl(el({ productId: "5" }, null)),
]));
"""
        with tempfile.TemporaryDirectory() as tmp:
            # .mjs copy: Node before 22 will not load ES module syntax from a
            # plain .js file without "type": "module" in package.json.
            module = Path(tmp) / "analytics.mjs"
            shutil.copyfile(ROOT / "static/development/utils/analytics.js", module)
            script = script % json.dumps(module.as_uri())
            path = Path(tmp) / "item_test.mjs"
            path.write_text(script, encoding="utf-8")
            out = subprocess.run(
                [NODE, str(path)], capture_output=True, text=True, encoding="utf-8", timeout=30
            )
        self.assertEqual(out.returncode, 0, out.stderr)
        chip_item, bare, explicit, no_group = json.loads(out.stdout)
        self.assertEqual(chip_item["item_id"], "44-300")
        self.assertEqual(chip_item["item_group_id"], "44")
        self.assertEqual(chip_item["item_variant"], "2.0x3.0")
        self.assertEqual(bare["item_id"], "44")
        self.assertEqual(explicit["item_id"], "44-9")
        self.assertEqual(no_group["item_id"], "5")
        self.assertNotIn("item_group_id", no_group)
