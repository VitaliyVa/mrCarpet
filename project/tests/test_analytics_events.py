"""
GA4 events rendered into pages.

Guards the parts that broke silently before:
  • inline view_item / view_cart printed numbers through the uk locale
    ("1799,1"), a JS syntax error, so those events never left the page;
  • `purchase` must stay server-side only (project/ga4_mp.py);
  • without GA configured every gtag()/mrTrack() call must be a no-op;
  • nothing personal may reach GA (core scrubber, checked under node).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings

from cart.models import Cart, CartProduct
from catalog.models import Product, ProductAttribute, ProductCategory, Size

ROOT = Path(settings.BASE_DIR)


def _json_script(html: str, element_id: str):
    m = re.search(
        rf'<script id="{element_id}" type="application/json">(.*?)</script>', html, re.S
    )
    return json.loads(m.group(1)) if m else None


class _CatalogData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = ProductCategory.objects.create(title="Сучасні", slug="suchasni-ga")
        cls.small = Size.objects.create(title="80x150")
        cls.big = Size.objects.create(title="160x230")
        cls.product = Product.objects.create(title="Килим Аналітика", slug="kylym-ga")
        cls.product.categories.add(cls.cat)
        cls.attr_small = ProductAttribute.objects.create(
            product=cls.product, size=cls.small, price=1000, quantity=3
        )
        # 1999 − 10 % = 1799.1: a non-integer price, the locale trap.
        cls.attr_big = ProductAttribute.objects.create(
            product=cls.product, size=cls.big, price=1999, discount=10, quantity=2
        )


@override_settings(GA4_MEASUREMENT_ID="G-TEST", GTM_CONTAINER_ID="")
class ViewItemTests(_CatalogData):
    def test_view_item_uses_selected_size_and_json(self):
        url = f"{self.product.get_absolute_url()}?size={self.attr_big.pk}"
        html = self.client.get(url).content.decode()
        item = _json_script(html, "ga4-view-item")
        self.assertIsNotNone(item, "view_item payload missing")
        # item_id is the Merchant feed g:id of the selected size.
        self.assertEqual(item["item_id"], f"{self.product.pk}-{self.attr_big.pk}")
        self.assertEqual(item["item_group_id"], str(self.product.pk))
        self.assertEqual(item["item_brand"], "mr.Carpet")
        self.assertEqual(item["item_variant"], "160x230")
        self.assertAlmostEqual(item["price"], 1799.1)
        self.assertEqual(item["currency"], "UAH")
        self.assertIn('mrTrackEcommerce("view_item"', html)
        # The old literal printed `price: 1799,1` — a syntax error in JS.
        self.assertNotIn("1799,1", html.split('id="ga4-view-item"')[1][:600])

    def test_list_context_on_related_and_category(self):
        html = self.client.get(self.cat.get_absolute_url()).content.decode()
        self.assertIn('data-ga-list-id="category_suchasni-ga"', html)
        self.assertIn('data-ga-item-category="Сучасні"', html)
        self.assertIn(f'data-catalog-product-id="{self.product.pk}"', html)


@override_settings(GA4_MEASUREMENT_ID="G-TEST", GTM_CONTAINER_ID="")
class CartEventTests(_CatalogData):
    def _with_cart(self):
        cart = Cart.objects.create()
        CartProduct.objects.create(cart=cart, product_attr=self.attr_big, quantity=2)
        session = self.client.session
        session["cart_id"] = cart.id
        session.save()
        return cart

    def test_view_cart_payload_is_json(self):
        self._with_cart()
        html = self.client.get("/cart/").content.decode()
        cart = _json_script(html, "ga4-cart-data")
        self.assertEqual(cart["currency"], "UAH")
        self.assertAlmostEqual(cart["value"], 3598.2)
        self.assertEqual(cart["items"][0]["item_id"], f"{self.product.pk}-{self.attr_big.pk}")
        self.assertEqual(cart["items"][0]["item_variant"], "160x230")
        self.assertEqual(cart["items"][0]["quantity"], 2)
        self.assertIn('var name = "view_cart"', html)
        # The cart page no longer loads the module file as a classic script.
        self.assertNotIn("/static/development/pages/promocode.js", html)

    def test_begin_checkout_on_checkout(self):
        self._with_cart()
        html = self.client.get("/checkout/").content.decode()
        self.assertIn('var name = "begin_checkout"', html)
        self.assertIsNotNone(_json_script(html, "ga4-cart-data"))


class AnalyticsHeadTests(SimpleTestCase):
    @override_settings(GA4_MEASUREMENT_ID="", GTM_CONTAINER_ID="")
    def test_off_mode_defines_noop_guard(self):
        html = render_to_string(
            "includes/analytics_head.html", {"ga4_measurement_id": "", "gtm_container_id": ""}
        )
        self.assertIn('window.__mrAnalyticsMode = "off"', html)
        self.assertIn('if (typeof w.gtag !== "function") w.gtag = function () {};', html)
        self.assertIn("w.mrTrack = track;", html)
        self.assertNotIn("googletagmanager.com/gtag/js", html)

    def test_gtag_mode_config_has_page_type_and_safe_location(self):
        html = render_to_string(
            "includes/analytics_head.html", {"ga4_measurement_id": "G-TEST"}
        )
        self.assertIn('window.__mrAnalyticsMode = "gtag"', html)
        self.assertIn("gtag('config', 'G", html)  # escapejs: G\u002DTEST
        self.assertIn("TEST', {", html)
        self.assertIn("page_type: window.__mrPageType", html)
        self.assertIn("page_location: window.__mrSafeLocation", html)

    def test_404_reports_page_not_found(self):
        html = render_to_string("404.html", {"ga4_measurement_id": "G-TEST"})
        self.assertIn('window.mrTrack("page_not_found"', html)
        self.assertIn("not_found", html)


class NoClientPurchaseTests(SimpleTestCase):
    """purchase is server-side only; a browser copy doubled the revenue."""

    PURCHASE_CALL = re.compile(
        r"""(trackEcommerce|mrTrackEcommerce|mrTrack|trackEvent)\(\s*["']purchase["']"""
        r"""|gtag\(\s*["']event["']\s*,\s*["']purchase["']"""
        r"""|event\s*:\s*["']purchase["']"""
    )

    def _files(self):
        yield from (ROOT / "templates").rglob("*.html")
        yield from (ROOT / "static" / "development").rglob("*.js")

    def test_no_purchase_event_in_sources(self):
        offenders = [
            str(p.relative_to(ROOT))
            for p in self._files()
            if self.PURCHASE_CALL.search(p.read_text(encoding="utf-8", errors="ignore"))
        ]
        self.assertEqual(offenders, [])

    def test_no_purchase_in_built_bundles(self):
        for bundle in (ROOT / "static" / "source" / "pages").glob("*/index.js"):
            text = bundle.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("ga4-purchase-data", text, bundle)
            self.assertIsNone(re.search(r'\(\s*"purchase"', text), bundle)


class BundleTests(SimpleTestCase):
    def test_helper_exports(self):
        src = (ROOT / "static/development/utils/analytics.js").read_text(encoding="utf-8")
        for name in (
            "export function trackEvent",
            "export function trackEcommerce",
            "export function itemFromProductEl",
            "export function trackFormError",
            "export function trackCheckoutSubmit",
            "window.mrAnalytics = api",
        ):
            self.assertIn(name, src)

    def test_bundles_are_rebuilt(self):
        """The bundle is what production serves (webpack does not run on deploy)."""
        for page, marker in (
            ("index", "view_item_list"),
            ("basket", "checkout_submit"),
            ("catalog_inside", "filter_use"),
            ("blog_inside", "article_read"),
            ("product", "gallery_open"),
        ):
            text = (ROOT / "static/source/pages" / page / "index.js").read_text(
                encoding="utf-8", errors="ignore"
            )
            self.assertIn(marker, text, page)


class BlogProductCardTests(_CatalogData):
    def test_cards_carry_item_fields(self):
        from blog.services.product_cards import render_block

        html = render_block([self.product.slug])
        self.assertIn('data-ga-list-id="blog_article"', html)
        self.assertIn(f'data-catalog-product-id="{self.product.pk}"', html)
        # Cheapest in-stock size, dot decimal (not the uk "1 000" display text).
        self.assertIn('data-price="1000.00"', html)
        self.assertIn('data-item-variant="80x150"', html)


NODE = shutil.which("node")


class CoreScrubberTests(SimpleTestCase):
    """Runs the inline core under node with a stub window."""

    def _run(self, js_body: str):
        html = render_to_string("includes/analytics_core.html", {})
        core = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        harness = """
var store = {};
var window = globalThis;
window.__h = {};
window.addEventListener = function (t, fn) { (window.__h[t] = window.__h[t] || []).push(fn); };
window.__mrAnalyticsMode = "off";
var document = { visibilityState: "visible", addEventListener: function () {} };
var location = { origin: "https://mrcarpet24.com", pathname: "/" };
var sessionStorage = { getItem: function (k) { return store[k] || null; },
  setItem: function (k, v) { store[k] = v; }, removeItem: function (k) { delete store[k]; } };
""" + core + js_body
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "core_test.js"
            script.write_text(harness, encoding="utf-8")
            out = subprocess.run(
                [NODE, str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def setUp(self):
        if not NODE:
            self.skipTest("node not installed")

    def test_pii_is_scrubbed_and_noop_without_ga(self):
        result = self._run(
            """
gtag("event", "x", {});  // no-op guard: must not throw
mrTrack("form_error", {
  form_name: "checkout",
  email: "a@b.com", phone: "+380 96 398 88 75", name: "Ольга",
  search_term: "килим для olga@mail.com 0963988875",
  filter_value: "1000-25000",
  items: [{ item_name: "Килим 80x150", price: 1799.1 }]
});
console.log(JSON.stringify(mrAnalyticsLog));
"""
        )
        params = result[0]["params"]
        self.assertEqual(result[0]["event"], "form_error")
        for key in ("email", "phone", "name"):
            self.assertNotIn(key, params)
        self.assertEqual(params["search_term"], "килим для [email] [phone]")
        self.assertEqual(params["filter_value"], "1000-25000")
        self.assertEqual(params["items"][0]["item_name"], "Килим 80x150")

    def test_js_errors_are_capped_and_deduped(self):
        result = self._run(
            """
var fire = function (e) { (window.__h.error || []).forEach(function (fn) { fn(e); }); };
fire({ message: "Boom", filename: "https://mrcarpet24.com/static/a.js?v=1", lineno: 3 });
fire({ message: "Boom", filename: "https://mrcarpet24.com/static/a.js?v=1", lineno: 3 });
fire({ message: "Script error.", filename: "", lineno: 0 });
fire({ message: "x", filename: "chrome-extension://abc/x.js", lineno: 1 });
for (var i = 0; i < 9; i++) fire({ message: "Err " + i + " for a@b.com", filename: "", lineno: i });
console.log(JSON.stringify(mrAnalyticsLog.filter(function (e) { return e.event === "js_error"; })));
"""
        )
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["params"]["error_message"], "Boom")
        self.assertEqual(result[0]["params"]["error_source"], "/static/a.js")
        self.assertEqual(result[1]["params"]["error_message"], "Err 0 for [email]")

    def test_once_is_per_page(self):
        result = self._run('console.log(JSON.stringify([mrTrackOnce("a"), mrTrackOnce("a")]));')
        self.assertEqual(result, [True, False])
