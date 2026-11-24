"""
Ad click attribution and "purchase only for real sales".

Cash on delivery used to count as a purchase the moment the order was placed,
so Google Ads bid on parcels nobody picked up, and no click id was stored, so
nothing could be corrected later. These tests pin the new behaviour:

  * the landing URL's gclid / gbraid / wbraid / utm_* survive to the order;
  * checkout sends `order_placed` for cash, `purchase` follows on paid /
    completed; card orders keep their LiqPay callback purchase;
  * the offline conversion export lists only real sales with a click id.
"""

from __future__ import annotations

import io
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from cart.models import Cart, CartProduct
from catalog.models import Product, ProductAttribute, Size
from order.ads_conversions import HEADER, conversion_rows, write_csv
from order.models import Order
from project.ad_attribution import (
    COOKIE_NAME,
    COOKIE_SALT,
    AdAttributionMiddleware,
    merge,
    order_fields_from_request,
    params_from_query,
    read_cookie,
)
from project.ga4_ecommerce import (
    cod_purchase_stage,
    order_is_real_sale,
    order_purchase_is_due,
    purchase_payload,
)

GCLID = "Cj0KCQiA_test-gclid.123"
GCLID_2 = "EAIaIQobChMI_second_click"


def _cookie(data):
    return signing.dumps(data, salt=COOKIE_SALT, compress=True)


class LandingParamsTests(SimpleTestCase):
    def test_click_ids_and_utm_are_read(self):
        out = params_from_query(
            {
                "gclid": GCLID,
                "utm_source": "google",
                "utm_medium": "cpc",
                "utm_campaign": "pmax-kylymy",
            }
        )
        self.assertEqual(out["gclid"], GCLID)
        self.assertEqual(out["utm_source"], "google")
        self.assertEqual(out["utm_campaign"], "pmax-kylymy")
        self.assertIsInstance(out["click_ts"], int)

    def test_junk_click_id_is_dropped(self):
        """A broken id only makes the Ads upload reject the row."""
        out = params_from_query({"gclid": "<script>alert(1)</script>"})
        self.assertEqual(out, {})
        self.assertEqual(params_from_query({"gclid": "short"}), {})

    def test_utm_is_trimmed_and_capped(self):
        out = params_from_query({"utm_source": "  news\nletter  " + "x" * 300})
        self.assertNotIn("\n", out["utm_source"])
        self.assertLessEqual(len(out["utm_source"]), 150)

    def test_no_params_no_attribution(self):
        self.assertEqual(params_from_query({"page": "2", "q": "килим"}), {})


class MergeTests(SimpleTestCase):
    def test_newsletter_visit_keeps_the_ads_click(self):
        current = {"gclid": GCLID, "click_ts": 1, "utm_source": "google"}
        merged = merge(current, {"utm_source": "newsletter"})
        self.assertEqual(merged["gclid"], GCLID)
        self.assertEqual(merged["utm_source"], "newsletter")

    def test_new_click_replaces_the_whole_click_group(self):
        current = {"gclid": GCLID, "click_ts": 1}
        merged = merge(current, {"gbraid": "GBRAID_value_123", "click_ts": 5})
        self.assertNotIn("gclid", merged)
        self.assertEqual(merged["gbraid"], "GBRAID_value_123")
        self.assertEqual(merged["click_ts"], 5)


class MiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.mw = AdAttributionMiddleware(lambda request: HttpResponse("ok"))

    def test_landing_with_gclid_sets_signed_cookie(self):
        response = self.mw(self.rf.get("/catalog/kylymy/", {"gclid": GCLID}))
        morsel = response.cookies[COOKIE_NAME]
        self.assertTrue(morsel["httponly"])
        self.assertEqual(morsel["samesite"], "Lax")
        self.assertEqual(int(morsel["max-age"]), 90 * 24 * 60 * 60)
        data = signing.loads(morsel.value, salt=COOKIE_SALT)
        self.assertEqual(data["gclid"], GCLID)

    def test_plain_visit_sets_nothing(self):
        response = self.mw(self.rf.get("/catalog/kylymy/"))
        self.assertNotIn(COOKIE_NAME, response.cookies)
        response = self.mw(self.rf.get("/catalog/kylymy/", {"page": "2"}))
        self.assertNotIn(COOKIE_NAME, response.cookies)

    def test_api_and_admin_are_skipped(self):
        for path in ("/api/create-order/", "/admin/order/order/"):
            response = self.mw(self.rf.get(path, {"gclid": GCLID}))
            self.assertNotIn(COOKIE_NAME, response.cookies, path)

    def test_post_is_skipped(self):
        response = self.mw(self.rf.post("/?gclid=" + GCLID))
        self.assertNotIn(COOKIE_NAME, response.cookies)

    def test_same_utm_again_does_not_rewrite_cookie(self):
        request = self.rf.get("/", {"utm_source": "google"})
        request.COOKIES[COOKIE_NAME] = _cookie({"utm_source": "google"})
        response = self.mw(request)
        self.assertNotIn(COOKIE_NAME, response.cookies)

    def test_tampered_cookie_is_ignored(self):
        request = self.rf.get("/")
        request.COOKIES[COOKIE_NAME] = "garbage:value"
        self.assertEqual(read_cookie(request), {})

    def test_page_never_breaks(self):
        """A failure inside attribution must not cost the visitor the page."""
        with patch("project.ad_attribution.params_from_query", side_effect=RuntimeError):
            response = self.mw(self.rf.get("/", {"gclid": GCLID}))
        self.assertEqual(response.status_code, 200)


class OrderFieldsTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_from_own_cookie(self):
        request = self.rf.get("/")
        ts = int(time.time()) - 3600
        request.COOKIES[COOKIE_NAME] = _cookie(
            {"gclid": GCLID, "click_ts": ts, "utm_source": "google", "utm_medium": "cpc"}
        )
        fields = order_fields_from_request(request)
        self.assertEqual(fields["gclid"], GCLID)
        self.assertEqual(fields["utm_medium"], "cpc")
        self.assertEqual(int(fields["ad_click_at"].timestamp()), ts)

    def test_falls_back_to_conversion_linker_cookie(self):
        """Visitors who landed before this shipped still carry _gcl_aw."""
        request = self.rf.get("/")
        request.COOKIES["_gcl_aw"] = f"GCL.1732456789.{GCLID}"
        request.COOKIES["_gcl_gb"] = "GCL.1732456700.GBRAID_value_123"
        fields = order_fields_from_request(request)
        self.assertEqual(fields["gclid"], GCLID)
        self.assertEqual(fields["gbraid"], "GBRAID_value_123")
        self.assertEqual(int(fields["ad_click_at"].timestamp()), 1732456789)

    def test_own_cookie_wins_over_linker(self):
        request = self.rf.get("/")
        request.COOKIES[COOKIE_NAME] = _cookie({"gclid": GCLID_2, "click_ts": 10})
        request.COOKIES["_gcl_aw"] = f"GCL.1732456789.{GCLID}"
        self.assertEqual(order_fields_from_request(request)["gclid"], GCLID_2)

    def test_malformed_linker_cookie_is_ignored(self):
        request = self.rf.get("/")
        request.COOKIES["_gcl_aw"] = "nonsense"
        self.assertEqual(order_fields_from_request(request), {})

    def test_no_request(self):
        self.assertEqual(order_fields_from_request(None), {})


class PurchaseRulesTests(SimpleTestCase):
    def _o(self, payment_type, status):
        return SimpleNamespace(payment_type=payment_type, status=status)

    def test_default_stage_is_delivery(self):
        self.assertEqual(cod_purchase_stage(), "delivery")

    def test_cod_is_a_sale_only_when_paid_or_completed(self):
        self.assertFalse(order_purchase_is_due(self._o("cash", "new")))
        self.assertFalse(order_purchase_is_due(self._o("cash", "shipped")))
        self.assertTrue(order_purchase_is_due(self._o("cash", "paid")))
        self.assertTrue(order_purchase_is_due(self._o("cash", "completed")))
        self.assertFalse(order_purchase_is_due(self._o("cash", "cancelled")))

    @override_settings(ADS_COD_PURCHASE_STAGE="order")
    def test_old_behaviour_can_be_switched_back(self):
        self.assertEqual(cod_purchase_stage(), "order")
        self.assertTrue(order_purchase_is_due(self._o("cash", "new")))

    def test_card_orders_unchanged(self):
        self.assertTrue(order_purchase_is_due(self._o("liqpay", "paid")))
        self.assertTrue(order_purchase_is_due(self._o("liqpay", "shipped")))
        self.assertFalse(order_purchase_is_due(self._o("liqpay", "awaiting_payment")))

    def test_real_sale_ignores_the_stage_setting(self):
        with override_settings(ADS_COD_PURCHASE_STAGE="order"):
            self.assertFalse(order_is_real_sale(self._o("cash", "new")))
            self.assertFalse(order_is_real_sale(self._o("cash", "shipped")))
        self.assertTrue(order_is_real_sale(self._o("liqpay", "shipped")))
        self.assertFalse(order_is_real_sale(self._o("liqpay", "awaiting_payment")))
        self.assertFalse(order_is_real_sale(None))

    def test_purchase_value_is_what_the_buyer_pays(self):
        """With a promocode the cart list price overstated revenue to tROAS."""

        class _QS(list):
            def prefetch_related(self, *a, **k):
                return self

        cart = SimpleNamespace(
            cart_products=SimpleNamespace(select_related=lambda *a, **k: _QS([])),
            get_total_price=lambda: 2000,
        )
        order = SimpleNamespace(order_number=1, payment_type="cash", total_price=1800.0)
        self.assertEqual(purchase_payload(order, cart)["value"], 1800.0)
        order = SimpleNamespace(order_number=1, payment_type="cash", total_price=None)
        self.assertEqual(purchase_payload(order, cart)["value"], 2000.0)


class _CartFixture:
    def _product_attr(self, price=1600, quantity=5):
        product = Product.objects.create(title="Килим тест", slug=f"kylym-ads-{Product.objects.count()}")
        size = Size.objects.create(title="1.6 x 2.3")
        return ProductAttribute.objects.create(
            product=product, size=size, price=price, quantity=quantity
        )

    def _order(self, *, payment_type=Order.PAYMENT_CASH, status=Order.STATUS_NEW, **extra):
        order = Order.objects.create(
            name="Оксана",
            surname="Тест",
            email="buyer@example.com",
            payment_type=payment_type,
            status=status,
            total_price=1600,
            **extra,
        )
        cart = Cart.objects.create(order=order)
        CartProduct.objects.create(cart=cart, product_attr=self._product_attr(), quantity=1)
        return order


@patch("order.api.views.enqueue_order_telegram")
@patch("order.api.views.enqueue_order_confirmation_email")
class CheckoutTests(_CartFixture, TestCase):
    def _checkout(self, payment_method, cookies=None):
        attr = self._product_attr()
        cart = Cart.objects.create()
        CartProduct.objects.create(cart=cart, product_attr=attr, quantity=1)
        session = self.client.session
        session["cart_id"] = cart.id
        session.save()
        for key, value in (cookies or {}).items():
            self.client.cookies[key] = value
        response = self.client.post(
            "/api/create-order/",
            {
                "name": "Оксана Тест",
                "email": "buyer@example.com",
                "phone": "+380501112233",
                "city": "Київ",
                "address": "Відділення 1",
                "payment_method": payment_method,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Order.objects.get(order_number=response.json()["order_number"])

    def test_cash_checkout_stores_click_and_sends_order_placed(self, *_):
        cookies = {
            COOKIE_NAME: _cookie(
                {"gclid": GCLID, "click_ts": int(time.time()), "utm_source": "google",
                 "utm_medium": "cpc", "utm_campaign": "pmax"}
            ),
            "_ga": "GA1.1.111.222",
        }
        with patch("project.ga4_mp.enqueue_order_placed_mp") as placed, patch(
            "project.ga4_mp.enqueue_order_purchase_mp"
        ) as purchase:
            order = self._checkout("cash", cookies)
        self.assertEqual(order.gclid, GCLID)
        self.assertEqual(order.utm_source, "google")
        self.assertEqual(order.utm_campaign, "pmax")
        self.assertIsNotNone(order.ad_click_at)
        self.assertEqual(order.ga4_client_id, "111.222")
        placed.assert_called_once_with(order.pk, client_id="111.222", session_id=None)
        purchase.assert_not_called()

    @override_settings(ADS_COD_PURCHASE_STAGE="order")
    def test_cash_checkout_old_stage_sends_purchase(self, *_):
        with patch("project.ga4_mp.enqueue_order_placed_mp") as placed, patch(
            "project.ga4_mp.enqueue_order_purchase_mp"
        ) as purchase:
            order = self._checkout("cash")
        purchase.assert_called_once_with(order.pk, client_id=None, session_id=None)
        placed.assert_not_called()

    def test_card_checkout_stores_click_and_sends_nothing_yet(self, *_):
        cookies = {"_gcl_aw": f"GCL.1732456789.{GCLID}"}
        with patch("project.ga4_mp.enqueue_order_placed_mp") as placed, patch(
            "project.ga4_mp.enqueue_order_purchase_mp"
        ) as purchase:
            order = self._checkout("card", cookies)
        self.assertEqual(order.status, Order.STATUS_AWAITING_PAYMENT)
        self.assertEqual(order.gclid, GCLID)
        placed.assert_not_called()
        purchase.assert_not_called()

    def test_checkout_without_attribution_leaves_fields_blank(self, *_):
        with patch("project.ga4_mp.enqueue_order_placed_mp"):
            order = self._checkout("cash")
        self.assertEqual(order.gclid, "")
        self.assertEqual(order.utm_source, "")
        self.assertIsNone(order.ad_click_at)

    def test_client_cannot_post_a_gclid(self, *_):
        """Click ids come only from the landing, never from the form body."""
        attr = self._product_attr()
        cart = Cart.objects.create()
        CartProduct.objects.create(cart=cart, product_attr=attr, quantity=1)
        session = self.client.session
        session["cart_id"] = cart.id
        session.save()
        with patch("project.ga4_mp.enqueue_order_placed_mp"):
            response = self.client.post(
                "/api/create-order/",
                {"name": "Оксана", "email": "buyer@example.com",
                 "payment_method": "cash", "gclid": GCLID, "utm_source": "fake"},
                content_type="application/json",
            )
        order = Order.objects.get(order_number=response.json()["order_number"])
        self.assertEqual(order.gclid, "")
        self.assertEqual(order.utm_source, "")


class CodPurchaseSignalTests(_CartFixture, TestCase):
    def _move(self, order, status):
        order.status = status
        order.save()

    def test_completed_cod_order_sends_purchase_with_stored_ids(self):
        order = self._order(ga4_client_id="111.222", ga4_session_id="1732456789")
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as purchase:
            self._move(order, Order.STATUS_COMPLETED)
        purchase.assert_called_once_with(
            order.pk, client_id="111.222", session_id="1732456789"
        )

    def test_paid_cod_order_sends_purchase(self):
        order = self._order()
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as purchase:
            self._move(order, Order.STATUS_PAID)
        purchase.assert_called_once()

    def test_shipped_is_not_a_sale_yet(self):
        order = self._order()
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as purchase:
            self._move(order, Order.STATUS_SHIPPED)
            self._move(order, Order.STATUS_CANCELLED)
        purchase.assert_not_called()

    def test_already_reported_order_is_not_sent_twice(self):
        """Orders from before the change got their purchase at creation."""
        order = self._order()
        Order.objects.filter(pk=order.pk).update(ga4_mp_sent=True)
        order.refresh_from_db()
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as purchase:
            self._move(order, Order.STATUS_COMPLETED)
        purchase.assert_not_called()

    def test_editing_a_completed_order_does_not_resend(self):
        order = self._order(status=Order.STATUS_COMPLETED)
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as purchase:
            order.phone = "+380671112233"
            order.save()
        purchase.assert_not_called()

    def test_card_orders_left_to_the_liqpay_callback(self):
        order = self._order(
            payment_type=Order.PAYMENT_LIQPAY, status=Order.STATUS_AWAITING_PAYMENT
        )
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as purchase:
            self._move(order, Order.STATUS_PAID)
        purchase.assert_not_called()

    @override_settings(ADS_COD_PURCHASE_STAGE="order")
    def test_old_stage_does_not_send_on_delivery(self):
        order = self._order()
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as purchase:
            self._move(order, Order.STATUS_COMPLETED)
        purchase.assert_not_called()


@override_settings(GA4_MEASUREMENT_ID="G-TEST", GA4_API_SECRET="secret")
class MeasurementProtocolTests(_CartFixture, TestCase):
    def _post_ok(self):
        return patch(
            "project.ga4_mp.requests.post",
            return_value=SimpleNamespace(status_code=204, text="", content=b""),
        )

    def test_new_cod_order_gets_no_purchase(self):
        from project.ga4_mp import send_order_purchase_mp

        order = self._order()
        with self._post_ok() as post:
            self.assertFalse(send_order_purchase_mp(order))
        post.assert_not_called()

    def test_completed_cod_order_gets_purchase_and_is_marked(self):
        from project.ga4_mp import send_order_purchase_mp

        order = self._order(status=Order.STATUS_COMPLETED)
        with self._post_ok() as post:
            self.assertTrue(send_order_purchase_mp(order))
        event = post.call_args.kwargs["json"]["events"][0]
        self.assertEqual(event["name"], "purchase")
        self.assertEqual(event["params"]["value"], 1600.0)
        order.refresh_from_db()
        self.assertTrue(order.ga4_mp_sent)

    def test_order_placed_event(self):
        from project.ga4_mp import send_order_placed_mp

        order = self._order(ga4_session_id="1732456789")
        with self._post_ok() as post:
            self.assertTrue(send_order_placed_mp(order))
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["events"][0]["name"], "order_placed")
        self.assertEqual(body["events"][0]["params"]["session_id"], "1732456789")
        self.assertEqual(
            body["events"][0]["params"]["transaction_id"], str(order.order_number)
        )
        order.refresh_from_db()
        # order_placed must not block the real purchase later.
        self.assertFalse(order.ga4_mp_sent)

    def test_enqueue_runs_after_commit(self):
        from project.ga4_mp import enqueue_order_placed_mp

        order = self._order()
        with patch("project.ga4_mp.threading.Thread") as thread:
            with self.captureOnCommitCallbacks(execute=True):
                enqueue_order_placed_mp(order.pk, client_id="1.2")
        thread.assert_called_once()

    def test_liqpay_callback_still_sends_purchase(self):
        from payment.utils import create_payment

        order = self._order(
            payment_type=Order.PAYMENT_LIQPAY, status=Order.STATUS_AWAITING_PAYMENT,
            ga4_client_id="5.6",
        )
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as purchase, patch(
            "order.email_utils.enqueue_order_confirmation_email"
        ), patch("project.telegram_utils.enqueue_order_telegram"):
            create_payment(None, {"status": "success", "order_id": str(order.pk)})
        purchase.assert_called_once_with(order.pk, client_id="5.6", session_id=None)


class OfflineExportTests(_CartFixture, TestCase):
    def _sale(self, **kw):
        defaults = dict(status=Order.STATUS_COMPLETED, gclid=GCLID)
        defaults.update(kw)
        return self._order(**defaults)

    def test_only_real_sales_with_click_are_listed(self):
        done = self._sale()
        self._sale(status=Order.STATUS_SHIPPED)  # COD on the way: not yet
        self._sale(status=Order.STATUS_NEW)
        self._sale(status=Order.STATUS_CANCELLED)
        self._sale(gclid="")  # no click
        card = self._sale(payment_type=Order.PAYMENT_LIQPAY, status=Order.STATUS_SHIPPED)
        self._sale(payment_type=Order.PAYMENT_LIQPAY, status=Order.STATUS_AWAITING_PAYMENT)
        rows = conversion_rows()
        ids = [r[5] for r in rows]
        self.assertEqual(sorted(ids), sorted([str(done.order_number), str(card.order_number)]))
        row = next(r for r in rows if r[5] == str(done.order_number))
        self.assertEqual(row[0], GCLID)
        self.assertEqual(row[1], "Оплачене замовлення")
        self.assertRegex(row[2], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\+0000$")
        self.assertEqual(row[3], "1600.00")
        self.assertEqual(row[4], "UAH")

    def test_braid_only_orders_need_the_flag(self):
        order = self._sale(gclid="", gbraid="GBRAID_value_123")
        self.assertEqual(conversion_rows(), [])
        rows = conversion_rows(with_braid=True)
        self.assertEqual(rows[0][0], "")
        self.assertEqual(rows[0][6:], ["GBRAID_value_123", ""])
        self.assertEqual(rows[0][5], str(order.order_number))

    def test_stale_click_is_skipped(self):
        self._sale(ad_click_at=timezone.now() - timedelta(days=120))
        self.assertEqual(conversion_rows(), [])

    def test_since_filters_old_conversions(self):
        order = self._sale()
        Order.objects.filter(pk=order.pk).update(
            completed_at=timezone.now() - timedelta(days=40)
        )
        self.assertEqual(conversion_rows(since=timezone.now() - timedelta(days=30)), [])
        self.assertEqual(len(conversion_rows()), 1)

    def test_csv_header(self):
        buf = io.StringIO()
        write_csv(buf, [])
        self.assertEqual(buf.getvalue().strip(), ",".join(HEADER))

    def test_command_writes_csv(self):
        self._sale()
        out, err = io.StringIO(), io.StringIO()
        call_command("export_ads_conversions", "--days", "7", stdout=out, stderr=err)
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(lines[0], ",".join(HEADER))
        self.assertEqual(len(lines), 2)
        self.assertIn(GCLID, lines[1])
        self.assertIn("1 conversions", err.getvalue())

    def test_admin_action_downloads_csv(self):
        user = get_user_model().objects.create_superuser(
            email="admin@example.com", password="pw-for-tests-only",

        )
        self.client.force_login(user)
        order = self._sale()
        response = self.client.post(
            "/admin/order/order/",
            {"action": "export_ads_conversions", "_selected_action": [order.pk]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(GCLID, response.content.decode("utf-8"))

    def test_admin_change_page_shows_attribution(self):
        user = get_user_model().objects.create_superuser(
            email="admin2@example.com", password="pw-for-tests-only",

        )
        self.client.force_login(user)
        order = self._sale(utm_source="google")
        response = self.client.get(f"/admin/order/order/{order.pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GCLID)
        self.assertContains(response, "Реклама: звідки прийшов покупець")
        listing = self.client.get("/admin/order/order/?ad_click=yes")
        self.assertEqual(listing.status_code, 200)
