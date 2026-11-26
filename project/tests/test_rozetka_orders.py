"""
Rozetka Marketplace order import (project/rozetka_api.py, rozetka_orders.py).

No network: `requests.request` inside project.rozetka_api is replaced by a fake
Rozetka that answers /sites and /orders/search from a dict.
"""

from __future__ import annotations

import base64
import io
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import requests
import yaml
from django.conf import settings
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase

from cart.models import CartProduct
from catalog.models import Product, ProductAttribute, Size
from order.ads_conversions import candidate_orders
from order.models import Order
from order.review_request import due_orders, due_orders_without_email
from project.admin import RozetkaSettingsAdmin, RozetkaSettingsForm
from project.ga4_ecommerce import order_is_real_sale, order_purchase_is_due
from project.models import RozetkaSettings, TelegramSettings
from project.rozetka_api import RozetkaClient, RozetkaError, encode_password
from project.rozetka_orders import (
    create_order,
    delivery_text,
    import_new_orders,
    normalize_phone,
    split_name,
)

ROOT = Path(settings.BASE_DIR)


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeRozetka:
    """Stands in for requests.request; records every call."""

    def __init__(self, orders=None, token="tok-1"):
        self.orders = orders or []
        self.token = token
        self.calls = []
        self.reject_next_authorized = 0  # answer 401 this many times

    def __call__(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.split("api-seller.rozetka.com.ua", 1)[1]
        self.calls.append(
            {"method": method, "path": path, "params": params, "json": json,
             "headers": headers, "timeout": timeout}
        )
        if path == "/sites":
            if json.get("username") != "seller@example.com":
                return FakeResponse({"success": False, "errors": {
                    "message": "incorrect_username_password", "code": 1004,
                    "description": "Неправильний логін або пароль", "details": None}})
            return FakeResponse({"success": True, "content": {"access_token": self.token}})
        if headers.get("Authorization") != f"Bearer {self.token}" or self.reject_next_authorized:
            self.reject_next_authorized = max(self.reject_next_authorized - 1, 0)
            return FakeResponse({"success": False, "errors": {"message": "unauthorized", "code": 401}}, 401)
        if path == "/orders/search":
            return FakeResponse({"success": True, "content": {
                "orders": deepcopy(self.orders),
                "_meta": {"totalCount": len(self.orders), "pageCount": 1, "currentPage": 1, "perPage": 20},
            }})
        if path.startswith("/orders/") and method == "GET":
            oid = int(path.rsplit("/", 1)[1])
            found = next(o for o in self.orders if o["id"] == oid)
            return FakeResponse({"success": True, "content": deepcopy(found)})
        if path.startswith("/orders/") and method == "PUT":
            return FakeResponse({"success": True, "content": {"id": 1, "status": json["status"]}})
        raise AssertionError(f"unexpected call {method} {path}")

    def paths(self):
        return [c["path"] for c in self.calls]


def rozetka_order(rid=248888186, offer="1x1", quantity=2, price="640.00", **extra):
    data = {
        "id": rid,
        "created": "2026-11-26 11:49:32",
        "amount": str(float(price) * quantity),
        "amount_with_discount": f"{float(price) * quantity:.2f}",
        "cost_with_discount": f"{float(price) * quantity + 70:.2f}",
        "status": 1,
        "status_group": 1,
        "comment": "Подзвоніть перед відправкою",
        "user_phone": "380954954374",
        "payment_type": "cash",
        "user": {"id": 39919762, "email": "buyer@example.com", "contact_fio": "Шевченко Юлія"},
        "delivery": {
            "delivery_service_id": 5,
            "delivery_service_name": "Нова Пошта",
            "recipient_title": "Шевченко Юлія Петрівна",
            "recipient_phone": "380950000000",
            "place_street": "",
            "place_number": "363",
            "place_house": "",
            "city": {"id": 1, "name": "Киев", "name_ua": "Київ"},
        },
        "purchases": [{
            "id": 158280800,
            "price": price,
            "price_with_discount": price,
            "cost": f"{float(price) * quantity:.2f}",
            "quantity": quantity,
            "item_id": 38221768,
            "item_name": "Килим Test 1.6 x 2.3",
            "item": {
                "id": 38221768,
                "name": "Килим Test",
                "article": offer,
                "price_offer_id": offer,
                "uploader_offer_id": offer,
            },
        }],
    }
    data.update(extra)
    return data


class RozetkaTestBase(TestCase):
    def setUp(self):
        self.product = Product.objects.create(title="Килим Test", slug="kylym-test")
        self.size = Size.objects.create(title="1.6 x 2.3")
        self.attr = ProductAttribute.objects.create(
            product=self.product, size=self.size, price=1000, quantity=5
        )
        self.offer = f"{self.product.pk}x{self.attr.pk}"
        self.cfg = RozetkaSettings.load()
        self.cfg.enabled = True
        self.cfg.username = "seller@example.com"
        self.cfg.password = "s3cret"
        self.cfg.save()

    def fake(self, *orders, **kwargs):
        fake = FakeRozetka(orders=list(orders), **kwargs)
        patcher = patch("project.rozetka_api.requests.request", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake


class ClientTests(RozetkaTestBase):
    def test_login_sends_base64_password_and_caches_token(self):
        fake = self.fake()
        client = RozetkaClient(RozetkaSettings.load())
        token = client.login()
        self.assertEqual(token, "tok-1")
        call = fake.calls[0]
        self.assertEqual(call["path"], "/sites")
        self.assertEqual(call["json"]["password"], base64.b64encode(b"s3cret").decode())
        self.assertEqual(call["timeout"], 20)
        self.assertEqual(RozetkaSettings.load().access_token, "tok-1")

    def test_wrong_credentials_raise(self):
        self.fake()
        self.cfg.username = "bad@example.com"
        self.cfg.save()
        with self.assertRaises(RozetkaError) as ctx:
            RozetkaClient(RozetkaSettings.load()).login()
        self.assertIn("1004", str(ctx.exception))

    def test_bearer_header_and_cached_token_reused_without_login(self):
        fake = self.fake()
        RozetkaSettings.objects.filter(pk=self.cfg.pk).update(access_token="tok-1")
        client = RozetkaClient(RozetkaSettings.load())
        client.search_orders()
        self.assertEqual(fake.paths(), ["/orders/search"])
        self.assertEqual(fake.calls[0]["headers"]["Authorization"], "Bearer tok-1")

    def test_expired_token_is_refreshed_once_and_call_repeated(self):
        fake = self.fake(token="tok-new")
        RozetkaSettings.objects.filter(pk=self.cfg.pk).update(access_token="tok-old")
        client = RozetkaClient(RozetkaSettings.load())
        orders, _meta = client.search_orders()
        self.assertEqual(orders, [])
        self.assertEqual(fake.paths(), ["/orders/search", "/sites", "/orders/search"])
        self.assertEqual(fake.calls[2]["headers"]["Authorization"], "Bearer tok-new")
        self.assertEqual(RozetkaSettings.load().access_token, "tok-new")

    def test_second_rejection_does_not_loop(self):
        fake = self.fake()
        fake.reject_next_authorized = 5
        client = RozetkaClient(RozetkaSettings.load())
        with self.assertRaises(RozetkaError):
            client.search_orders()
        self.assertLessEqual(len(fake.calls), 4)

    def test_change_status_puts_status(self):
        fake = self.fake()
        RozetkaClient(RozetkaSettings.load()).change_status(555, 2, seller_comment="ok")
        put = [c for c in fake.calls if c["method"] == "PUT"][0]
        self.assertEqual(put["path"], "/orders/555")
        self.assertEqual(put["json"], {"status": 2, "seller_comment": "ok"})

    def test_network_error_is_a_rozetka_error(self):
        with patch("project.rozetka_api.requests.request",
                   side_effect=requests.ConnectTimeout("slow")):
            with self.assertRaises(RozetkaError):
                RozetkaClient(RozetkaSettings.load()).login()

    def test_encode_password(self):
        self.assertEqual(encode_password("ab"), "YWI=")


class ParsingTests(SimpleTestCase):
    def test_phone(self):
        self.assertEqual(normalize_phone("380954954374"), "+380954954374")
        self.assertEqual(normalize_phone("0954954374"), "+380954954374")
        self.assertEqual(normalize_phone("+38 (095) 495-43-74"), "+380954954374")
        self.assertEqual(normalize_phone(None), "")

    def test_name_is_surname_first(self):
        self.assertEqual(split_name("Шевченко Юлія Петрівна"), ("Юлія", "Шевченко"))
        self.assertEqual(split_name("Юлія"), ("Юлія", "Юлія"))
        self.assertEqual(split_name("")[0], "Покупець Rozetka")

    def test_delivery_text(self):
        city, text = delivery_text(
            {"delivery_service_name": "Нова Пошта", "place_number": "363",
             "city": {"name_ua": "Київ"}}
        )
        self.assertEqual((city, text), ("Київ", "Нова Пошта №363"))
        city, text = delivery_text(
            {"delivery_service_name": "Кур'єр", "place_street": "вул. Лесі",
             "place_house": "5", "place_flat": "12", "city": {"name": "Львів"}}
        )
        self.assertEqual(city, "Львів")
        self.assertEqual(text, "Кур'єр, вул. Лесі, 5, кв. 12")


class ImportTests(RozetkaTestBase):
    def setUp(self):
        super().setUp()
        tg = TelegramSettings.load()
        tg.is_enabled = True
        tg.bot_token = "123:abc"
        tg.chat_id = "-100"
        tg.save()
        patcher = patch("project.telegram_utils.send_telegram_message_async")
        self.tg_send = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("project.telegram_utils._remember_agent_notify")
        patcher.start()
        self.addCleanup(patcher.stop)

    def order_payload(self, **kwargs):
        return rozetka_order(offer=self.offer, **kwargs)

    def test_creates_order_with_customer_delivery_and_items(self):
        self.fake(self.order_payload())
        summary = import_new_orders()
        self.assertEqual((summary["created"], summary["errors"]), (1, []))

        order = Order.objects.get()
        self.assertEqual(order.source, "rozetka")
        self.assertEqual(order.rozetka_order_id, 248888186)
        self.assertEqual(order.order_number, 248888186)
        self.assertEqual(order.status, Order.STATUS_NEW)
        self.assertEqual((order.name, order.surname), ("Юлія", "Шевченко"))
        self.assertEqual(order.phone, "+380950000000")
        self.assertEqual(order.email, "buyer@example.com")
        self.assertEqual(order.city, "Київ")
        self.assertEqual(order.address, "Нова Пошта №363")
        self.assertEqual(order.payment_type, Order.PAYMENT_CASH)
        self.assertEqual(order.total_price, 1280.0)
        self.assertIn("Подзвоніть", order.message)
        self.assertIn("+380954954374", order.message)  # buyer phone differs from recipient
        item = CartProduct.objects.get(cart__order=order)
        self.assertEqual((item.product_attr_id, item.quantity), (self.attr.pk, 2))

    def test_prepaid_order_gets_rozetka_payment_type(self):
        self.fake(self.order_payload(payment_type="card"))
        import_new_orders()
        self.assertEqual(Order.objects.get().payment_type, Order.PAYMENT_ROZETKA)

    def test_second_poll_does_not_duplicate_or_renotify(self):
        self.fake(self.order_payload())
        import_new_orders()
        again = import_new_orders()
        self.assertEqual((again["created"], again["skipped"]), (0, 1))
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(CartProduct.objects.count(), 1)
        self.assertEqual(self.tg_send.call_count, 1)
        self.attr.refresh_from_db()
        self.assertEqual(self.attr.quantity, 3)  # taken once, not twice

    def test_create_order_direct_is_idempotent(self):
        data = self.order_payload()
        self.assertIsNotNone(create_order(data))
        self.assertIsNone(create_order(data))
        self.assertEqual(Order.objects.count(), 1)

    def test_stock_is_decreased_like_the_site_checkout(self):
        self.fake(self.order_payload(quantity=2))
        import_new_orders()
        self.attr.refresh_from_db()
        self.assertEqual(self.attr.quantity, 3)

    def test_oversold_stock_clamps_at_zero_and_is_noted(self):
        self.fake(self.order_payload(quantity=8))
        import_new_orders()
        self.attr.refresh_from_db()
        self.assertEqual(self.attr.quantity, 0)
        order = Order.objects.get()
        self.assertIn("Недостатньо залишку", order.message)
        self.assertEqual(CartProduct.objects.get(cart__order=order).quantity, 8)

    def test_unknown_offer_id_still_creates_the_order_with_a_note(self):
        payload = rozetka_order(rid=777, offer="999999x888888")
        self.fake(payload)
        summary = import_new_orders()
        self.assertEqual((summary["created"], summary["errors"]), (1, []))
        order = Order.objects.get(rozetka_order_id=777)
        self.assertEqual(CartProduct.objects.filter(cart__order=order).count(), 0)
        self.assertIn("Не знайдено в каталозі", order.message)
        self.assertIn("999999x888888", order.message)
        self.assertEqual(order.total_price, 1280.0)
        self.attr.refresh_from_db()
        self.assertEqual(self.attr.quantity, 5)
        self.assertEqual(self.tg_send.call_count, 1)

    def test_offer_id_of_a_different_product_is_not_matched(self):
        wrong = f"{self.product.pk + 100}x{self.attr.pk}"
        self.fake(rozetka_order(rid=778, offer=wrong))
        import_new_orders()
        self.assertEqual(CartProduct.objects.count(), 0)

    def test_failed_orders_are_skipped(self):
        self.fake(self.order_payload(status_group=3, status=19))
        summary = import_new_orders()
        self.assertEqual((summary["created"], summary["skipped"]), (0, 1))
        self.assertFalse(Order.objects.exists())

    def test_purchases_missing_in_list_are_fetched_by_id(self):
        payload = self.order_payload()
        listing = deepcopy(payload)
        del listing["purchases"]
        fake = self.fake(payload)
        fake.orders = [payload]
        # search answers without purchases, GET /orders/{id} has them
        original = fake.__call__

        def search_without_purchases(method, url, **kw):
            response = original(method, url, **kw)
            if url.endswith("/orders/search"):
                for o in response._payload["content"]["orders"]:
                    o.pop("purchases", None)
            return response

        with patch("project.rozetka_api.requests.request", search_without_purchases):
            import_new_orders()
        self.assertEqual(CartProduct.objects.count(), 1)

    def test_telegram_gets_the_site_message_prefixed_with_rozetka(self):
        self.fake(self.order_payload())
        import_new_orders()
        self.assertEqual(self.tg_send.call_count, 1)
        text = self.tg_send.call_args.args[0]
        self.assertTrue(text.startswith("ROZETKA"), text)
        self.assertIn("Нове замовлення №248888186", text)
        self.assertIn("Київ", text)
        self.assertIn("Килим Test", text)
        self.assertEqual(self.tg_send.call_args.kwargs.get("parse_mode"), "HTML")

    def test_site_order_message_has_no_rozetka_prefix(self):
        from project.telegram_utils import format_order_message

        order = Order.objects.create(
            name="A", surname="B", payment_type=Order.PAYMENT_CASH, total_price=1
        )
        self.assertNotIn("ROZETKA", format_order_message(order))

    def test_no_ga4_ads_or_review_for_rozetka_orders(self):
        self.fake(self.order_payload())
        import_new_orders()
        order = Order.objects.get()
        Order.objects.filter(pk=order.pk).update(
            status=Order.STATUS_COMPLETED,
            gclid="abc",
            completed_at="2020-01-01T00:00:00Z",
        )
        order.refresh_from_db()
        self.assertFalse(order_purchase_is_due(order))
        self.assertFalse(order_is_real_sale(order))
        self.assertEqual(list(candidate_orders()), [])
        self.assertEqual(list(due_orders()), [])
        self.assertEqual(list(due_orders_without_email()), [])

        from project.ga4_mp import send_order_placed_mp, send_order_purchase_mp

        with patch("project.ga4_mp.send_mp_purchase") as send, \
                patch("project.ga4_mp.mp_configured", return_value=True):
            self.assertFalse(send_order_purchase_mp(order, force=True))
            self.assertFalse(send_order_placed_mp(order))
        send.assert_not_called()

        # saving a rozetka cash order through a status change must not enqueue GA4
        with patch("project.ga4_mp.enqueue_order_purchase_mp") as enqueue:
            order.status = Order.STATUS_PAID
            order.save()
        enqueue.assert_not_called()

    def test_site_orders_keep_their_ads_and_ga4_behaviour(self):
        order = Order.objects.create(
            name="A", surname="B", payment_type=Order.PAYMENT_LIQPAY,
            status=Order.STATUS_PAID, gclid="abc", total_price=100,
        )
        self.assertTrue(order_purchase_is_due(order))
        self.assertEqual(list(candidate_orders()), [order])


class SplitSearchRozetka(FakeRozetka):
    """/orders/search answers the created_from window and the late failed-orders
    search (types=6) from separate lists, like the real API filters them."""

    def __init__(self, window=None, failed=None, **kwargs):
        super().__init__(orders=list(window or []), **kwargs)
        self.window = list(window or [])
        self.failed = list(failed or [])

    def __call__(self, method, url, params=None, **kwargs):
        if url.endswith("/orders/search"):
            self.orders = self.failed if (params or {}).get("types") == 6 else self.window
        elif url.rsplit("/", 1)[-1].isdigit():
            self.orders = self.window + self.failed
        return super().__call__(method, url, params=params, **kwargs)


class CancellationTests(RozetkaTestBase):
    def setUp(self):
        super().setUp()
        tg = TelegramSettings.load()
        tg.is_enabled = True
        tg.bot_token = "123:abc"
        tg.chat_id = "-100"
        tg.save()
        patcher = patch("project.telegram_utils.send_telegram_message_async")
        self.tg_send = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("project.telegram_utils._remember_agent_notify")
        patcher.start()
        self.addCleanup(patcher.stop)

    def import_then_fail(self, **kwargs):
        fake = self.fake(rozetka_order(offer=self.offer, **kwargs))
        self.assertEqual(import_new_orders()["created"], 1)
        self.tg_send.reset_mock()
        fake.orders[0]["status_group"] = 3
        fake.orders[0]["status"] = 19
        return fake

    def stock(self, attr=None):
        attr = attr or self.attr
        attr.refresh_from_db()
        return attr.quantity

    def test_cancel_returns_stock_exactly_once(self):
        self.import_then_fail(quantity=2)
        self.assertEqual(self.stock(), 3)

        first = import_new_orders()
        self.assertEqual((first["cancelled"], first["created"], first["errors"]), (1, 0, []))
        order = Order.objects.get()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertIn("Rozetka скасувала замовлення, залишок повернено", order.message)
        self.assertEqual(self.stock(), 5)

        second = import_new_orders()
        self.assertEqual((second["cancelled"], second["skipped"]), (0, 1))
        self.assertEqual(self.stock(), 5)
        self.assertEqual(self.tg_send.call_count, 1)

    def test_already_cancelled_order_is_not_touched(self):
        self.import_then_fail(quantity=2)
        order = Order.objects.get()
        order.status = Order.STATUS_CANCELLED  # manager cancelled it in the admin
        order.save()
        message = Order.objects.get().message

        summary = import_new_orders()
        self.assertEqual(summary["cancelled"], 0)
        self.assertEqual(self.stock(), 3)
        self.assertEqual(Order.objects.get().message, message)
        self.tg_send.assert_not_called()

    def test_oversold_order_returns_only_what_was_taken(self):
        self.import_then_fail(quantity=8)  # 5 in stock, Rozetka sold 8
        self.assertEqual(self.stock(), 0)
        self.assertEqual(import_new_orders()["cancelled"], 1)
        self.assertEqual(self.stock(), 5)  # not 8

    def test_oversold_note_matches_its_own_line_only(self):
        other_product = Product.objects.create(title="Килим Other", slug="kylym-other")
        other = ProductAttribute.objects.create(
            product=other_product, size=self.size, price=500, quantity=10
        )
        payload = rozetka_order(offer=self.offer, quantity=8)
        line = deepcopy(payload["purchases"][0])
        offer2 = f"{other_product.pk}x{other.pk}"
        line["item"].update(article=offer2, price_offer_id=offer2, uploader_offer_id=offer2)
        line["quantity"] = 3
        payload["purchases"].append(line)
        fake = self.fake(payload)
        import_new_orders()
        self.assertEqual((self.stock(), self.stock(other)), (0, 7))

        fake.orders[0]["status_group"] = 3
        import_new_orders()
        self.assertEqual((self.stock(), self.stock(other)), (5, 10))

    def test_unknown_failed_order_is_ignored(self):
        self.fake(rozetka_order(rid=555, offer=self.offer, status_group=3, status=19))
        summary = import_new_orders()
        self.assertEqual((summary["cancelled"], summary["created"], summary["skipped"]), (0, 0, 1))
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.stock(), 5)
        self.tg_send.assert_not_called()

    def test_site_order_with_same_number_is_not_cancelled(self):
        Order.objects.create(
            name="A", surname="B", payment_type=Order.PAYMENT_CASH, total_price=1,
            rozetka_order_id=556,
        )
        self.fake(rozetka_order(rid=556, offer=self.offer, status_group=3))
        self.assertEqual(import_new_orders()["cancelled"], 0)
        self.assertEqual(Order.objects.get().status, Order.STATUS_NEW)

    def test_telegram_gets_a_short_cancel_line(self):
        self.import_then_fail()
        import_new_orders()
        self.assertEqual(self.tg_send.call_count, 1)
        text = self.tg_send.call_args.args[0]
        self.assertTrue(
            text.startswith("ROZETKA ❌ Замовлення №248888186 скасовано, залишок повернено"), text
        )
        self.assertIn("/admin/order/order/", text)

    def test_telegram_respects_the_orders_switch(self):
        self.import_then_fail()
        TelegramSettings.objects.update(notify_orders=False)
        self.assertEqual(import_new_orders()["cancelled"], 1)
        self.tg_send.assert_not_called()

    def test_custom_length_line_takes_and_returns_nothing(self):
        self.attr.custom_attribute = True
        self.attr.save()
        self.import_then_fail(quantity=2)
        self.assertEqual(self.stock(), 5)
        self.assertEqual(import_new_orders()["cancelled"], 1)
        self.assertEqual(self.stock(), 5)
        self.assertEqual(CartProduct.objects.count(), 1)
        self.assertNotIn("залишок повернено", Order.objects.get().message)
        self.assertIn("залишок не змінювався", self.tg_send.call_args.args[0])

    def test_late_cancellation_outside_the_window_is_found(self):
        payload = rozetka_order(offer=self.offer, quantity=2)
        fake = SplitSearchRozetka(window=[payload])
        patcher = patch("project.rozetka_api.requests.request", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        import_new_orders()
        self.assertEqual(self.stock(), 3)

        failed = deepcopy(payload)
        failed.update(status_group=3, status=19, created="2026-11-01 10:00:00")
        fake.window, fake.failed = [], [failed]
        summary = import_new_orders()
        self.assertEqual((summary["cancelled"], summary["errors"]), (1, []))
        self.assertEqual(self.stock(), 5)
        late = [c for c in fake.calls if c["path"] == "/orders/search"
                and (c["params"] or {}).get("types") == 6]
        self.assertTrue(late)
        self.assertIn("status_updated_from", late[-1]["params"])
        self.assertNotIn("created_from", late[-1]["params"])

        again = import_new_orders()
        self.assertEqual(again["cancelled"], 0)
        self.assertEqual(self.stock(), 5)

    def test_late_search_ignores_orders_we_never_imported(self):
        stranger = rozetka_order(rid=999, offer=self.offer, status_group=3)
        fake = SplitSearchRozetka(failed=[stranger])
        patcher = patch("project.rozetka_api.requests.request", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        summary = import_new_orders()
        self.assertEqual((summary["cancelled"], summary["skipped"], summary["errors"]), (0, 0, []))
        self.assertFalse(Order.objects.exists())


class PollerBehaviourTests(RozetkaTestBase):
    def test_disabled_settings_do_nothing_and_make_no_http_call(self):
        self.cfg.enabled = False
        self.cfg.save()
        fake = self.fake(rozetka_order(offer=self.offer))
        summary = import_new_orders()
        self.assertTrue(summary["disabled"])
        self.assertEqual(fake.calls, [])
        self.assertFalse(Order.objects.exists())
        self.assertIsNone(RozetkaSettings.load().last_poll_at)

    def test_missing_credentials_do_nothing(self):
        self.cfg.password = ""
        self.cfg.save()
        fake = self.fake()
        self.assertTrue(import_new_orders()["disabled"])
        self.assertEqual(fake.calls, [])

    def test_api_failure_is_recorded_not_raised(self):
        with patch("project.rozetka_api.requests.request",
                   side_effect=requests.ConnectionError("down")):
            summary = import_new_orders()
        self.assertEqual(summary["created"], 0)
        self.assertTrue(summary["errors"])
        cfg = RozetkaSettings.load()
        self.assertIn("down", cfg.last_error)
        self.assertIsNotNone(cfg.last_poll_at)

    def test_success_clears_last_error(self):
        RozetkaSettings.objects.filter(pk=self.cfg.pk).update(last_error="old problem")
        self.fake()
        import_new_orders()
        cfg = RozetkaSettings.load()
        self.assertEqual(cfg.last_error, "")
        self.assertIsNotNone(cfg.last_poll_at)

    def test_one_bad_order_does_not_block_the_next(self):
        good = rozetka_order(rid=2, offer=self.offer)
        bad = rozetka_order(rid=1, offer=self.offer)
        bad["id"] = "not-a-number"
        self.fake(bad, good)
        summary = import_new_orders()
        self.assertEqual(summary["created"], 1)
        self.assertEqual(len(summary["errors"]), 1)
        self.assertTrue(Order.objects.filter(rozetka_order_id=2).exists())

    def test_search_uses_a_created_from_window(self):
        fake = self.fake()
        import_new_orders()
        search = [c for c in fake.calls if c["path"] == "/orders/search"][0]
        self.assertIn("created_from", search["params"])
        self.assertIn("purchases", search["params"]["expand"])

    def test_command_once(self):
        self.fake(rozetka_order(offer=self.offer))
        out = io.StringIO()
        with patch("project.telegram_utils.notify_order"):
            call_command("rozetka_poll", once=True, stdout=out)
        self.assertIn("created 1", out.getvalue())
        self.assertEqual(Order.objects.count(), 1)

    def test_command_once_disabled(self):
        self.cfg.enabled = False
        self.cfg.save()
        out = io.StringIO()
        call_command("rozetka_poll", once=True, stdout=out)
        self.assertIn("disabled", out.getvalue())

    def test_interval_is_clamped(self):
        cfg = RozetkaSettings(poll_minutes=0)
        self.assertEqual(cfg.interval_seconds, 60)
        cfg.poll_minutes = 500
        self.assertEqual(cfg.interval_seconds, 3600)


class AdminTests(TestCase):
    def test_password_is_never_rendered_and_blank_keeps_it(self):
        cfg = RozetkaSettings.load()
        cfg.password = "s3cret"
        cfg.username = "seller@example.com"
        cfg.save()
        form = RozetkaSettingsForm(instance=cfg)
        self.assertNotIn("s3cret", str(form["password"]))
        form = RozetkaSettingsForm(
            data={"enabled": "on", "username": "seller@example.com",
                  "password": "", "poll_minutes": 2},
            instance=cfg,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        cfg.refresh_from_db()
        self.assertEqual(cfg.password, "s3cret")
        self.assertTrue(cfg.enabled)

    def test_new_password_replaces_it_and_drops_cached_token(self):
        cfg = RozetkaSettings.load()
        cfg.password = "old"
        cfg.access_token = "tok"
        cfg.save()
        form = RozetkaSettingsForm(
            data={"enabled": "", "username": "", "password": "new", "poll_minutes": 3},
            instance=cfg,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        cfg.refresh_from_db()
        self.assertEqual((cfg.password, cfg.access_token), ("new", ""))

    def test_poll_minutes_range(self):
        form = RozetkaSettingsForm(
            data={"username": "u", "password": "p", "poll_minutes": 120},
            instance=RozetkaSettings.load(),
        )
        self.assertFalse(form.is_valid())

    def test_admin_page_opens_and_hides_password(self):
        from django.contrib.auth import get_user_model

        cfg = RozetkaSettings.load()
        cfg.password = "s3cret-value"
        cfg.save()
        user = get_user_model().objects.create_superuser(email="a@example.com", password="x")
        self.client.force_login(user)
        response = self.client.get(f"/admin/project/rozetkasettings/{cfg.pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "s3cret-value")


class InfraTests(SimpleTestCase):
    def test_compose_service_and_deploy_line(self):
        compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
        service = compose["services"]["rozetka-poller"]
        self.assertEqual(service["command"], "python manage.py rozetka_poll")
        self.assertEqual(service["restart"], "unless-stopped")
        deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        self.assertRegex(deploy, r"up -d ga4-weekly content-scheduler rozetka-poller\b")
