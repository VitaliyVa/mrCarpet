"""Stock sync site -> Rozetka (project/rozetka_stock.py), HTTP mocked."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import Product, ProductAttribute, ProductImage, Size
from project.merchant_feed import feed_products
from project.models import RozetkaItem, RozetkaSettings
from project.prom_feed import build_rozetka_offers
from project.rozetka_stock import BATCH_SIZE, feed_stock_quantities, sync_stock
from project.tests.test_merchant_feed import _make_product


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeRozetka:
    """Stands in for requests.request: /sites, /goods/all, /items/mass-update."""

    def __init__(self, goods=None, token="tok-1"):
        self.goods = goods or []
        self.token = token
        self.calls = []
        self.put_reply = None  # callable(items) -> FakeResponse, default success
        self.reject_next_authorized = 0

    def __call__(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.split("api-seller.rozetka.com.ua", 1)[1]
        self.calls.append({"method": method, "path": path, "params": params, "json": json})
        if path == "/sites":
            return FakeResponse({"success": True, "content": {"access_token": self.token}})
        if headers.get("Authorization") != f"Bearer {self.token}" or self.reject_next_authorized:
            self.reject_next_authorized = max(self.reject_next_authorized - 1, 0)
            return FakeResponse({"success": False, "errors": {"message": "unauthorized", "code": 401}}, 401)
        if path == "/goods/all" and method == "GET":
            size = int(params.get("pageSize") or 100)
            page = int(params.get("page") or 1)
            rows = self.goods[(page - 1) * size:page * size]
            page_count = max((len(self.goods) + size - 1) // size, 1)
            return FakeResponse({"success": True, "content": {
                "items": rows,
                "_meta": {"totalCount": len(self.goods), "pageCount": page_count,
                          "currentPage": page, "perPage": size},
            }})
        if path == "/items/mass-update" and method == "PUT":
            if self.put_reply:
                return self.put_reply(json["items"])
            return FakeResponse({"success": True, "content": None})
        raise AssertionError(f"unexpected call {method} {path}")

    def count(self, path):
        return sum(1 for c in self.calls if c["path"] == path)

    def sent(self):
        """All items sent through mass-update, in order."""
        return [i for c in self.calls if c["path"] == "/items/mass-update" for i in c["json"]["items"]]


@override_settings(SITE_URL="https://mrcarpet24.com", ROZETKA_PRICE_MARKUP="1.25")
class StockSyncTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # small: 600 UAH, qty 3; big: qty 0; plus a custom-length attr (not in feed)
        _make_product(cls)
        ProductImage.objects.create(product=cls.product, image="products/gallery 1.jpg")
        cls.custom = cls.product.product_attr.get(custom_attribute=True)

    def setUp(self):
        self.cfg = RozetkaSettings.load()
        self.cfg.enabled = True
        self.cfg.username = "seller@example.com"
        self.cfg.password = "secret"
        self.cfg.access_token = "tok-1"
        self.cfg.save()
        self.offer_small = f"{self.product.pk}x{self.small.pk}"
        self.offer_big = f"{self.product.pk}x{self.big.pk}"
        self.offer_custom = f"{self.product.pk}x{self.custom.pk}"
        self.fake = FakeRozetka(goods=[
            {"rz_item_id": 1001, "price_offer_id": self.offer_small, "item_id": 1},
            {"rz_item_id": 1002, "price_offer_id": self.offer_big, "item_id": 2},
        ])
        patcher = patch("project.rozetka_api.requests.request", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def item(self, rz_id):
        return RozetkaItem.objects.get(rz_item_id=rz_id)


class MapRefreshTests(StockSyncTestBase):
    def test_first_pass_builds_map_and_sets_refreshed_at(self):
        self.fake.goods += [
            {"rz_item_id": None, "price_offer_id": "9x9"},  # no Rozetka id
            {"rz_item_id": 1003, "price_offer_id": ""},  # no offer id
            {"rz_item_id": 1004, "price_offer_id": "ART-77"},  # not our feed id
        ]
        sync_stock()
        self.assertEqual(
            dict(RozetkaItem.objects.values_list("rz_item_id", "offer_id")),
            {1001: self.offer_small, 1002: self.offer_big},
        )
        self.cfg.refresh_from_db()
        self.assertIsNotNone(self.cfg.items_refreshed_at)
        self.assertEqual(self.fake.count("/goods/all"), 1)

    def test_goods_list_is_read_once_per_six_hours(self):
        sync_stock()
        sync_stock()
        self.assertEqual(self.fake.count("/goods/all"), 1)
        RozetkaSettings.objects.filter(pk=self.cfg.pk).update(
            items_refreshed_at=timezone.now() - timedelta(hours=6, minutes=1)
        )
        sync_stock()
        self.assertEqual(self.fake.count("/goods/all"), 2)

    def test_pages_are_all_read(self):
        self.fake.goods = [
            {"rz_item_id": 5000 + n, "price_offer_id": f"{900000 + n}x1"} for n in range(250)
        ]
        sync_stock()
        self.assertEqual(RozetkaItem.objects.count(), 250)
        self.assertEqual(self.fake.count("/goods/all"), 3)

    def test_refresh_updates_changed_offer_and_drops_vanished_items(self):
        RozetkaItem.objects.create(rz_item_id=1001, offer_id="1x1", last_quantity=3)
        RozetkaItem.objects.create(rz_item_id=7777, offer_id="2x2", last_quantity=0)
        sync_stock()
        self.assertEqual(self.item(1001).offer_id, self.offer_small)
        self.assertEqual(self.item(1001).last_quantity, 3)  # sent again with the new offer
        self.assertFalse(RozetkaItem.objects.filter(rz_item_id=7777).exists())

    def test_empty_goods_answer_keeps_existing_map(self):
        RozetkaItem.objects.create(rz_item_id=1001, offer_id=self.offer_small, last_quantity=3)
        self.fake.goods = []
        sync_stock()
        self.assertTrue(RozetkaItem.objects.filter(rz_item_id=1001).exists())

    def test_refresh_error_is_reported_and_known_items_still_synced(self):
        RozetkaItem.objects.create(rz_item_id=1001, offer_id=self.offer_small)
        real = self.fake.__call__

        def fake(method, url, **kwargs):
            if "/goods/all" in url:
                return FakeResponse({"success": False, "errors": {
                    "message": "server_error", "code": 0, "description": "boom"}})
            return real(method, url, **kwargs)

        with patch("project.rozetka_api.requests.request", fake):
            result = sync_stock()
        self.assertEqual(result["updated"], 1)
        self.assertTrue(any("список товарів" in e for e in result["errors"]))
        self.cfg.refresh_from_db()
        self.assertIsNone(self.cfg.items_refreshed_at)  # retried next pass


class StockPushTests(StockSyncTestBase):
    def test_first_pass_sends_feed_quantities_without_price(self):
        result = sync_stock()
        self.assertEqual(result, {"updated": 2, "errors": []})
        self.assertEqual(
            sorted(self.fake.sent(), key=lambda i: i["item_rz_id"]),
            [{"item_rz_id": 1001, "stock_quantity": 3}, {"item_rz_id": 1002, "stock_quantity": 0}],
        )
        self.assertEqual(self.item(1001).last_quantity, 3)
        self.assertEqual(self.item(1002).last_quantity, 0)
        self.assertIsNotNone(self.item(1001).synced_at)

    def test_only_changed_items_are_sent(self):
        sync_stock()
        before = self.fake.count("/items/mass-update")
        self.assertEqual(sync_stock(), {"updated": 0, "errors": []})
        self.assertEqual(self.fake.count("/items/mass-update"), before)  # nothing changed, no call

        ProductAttribute.objects.filter(pk=self.small.pk).update(quantity=2)  # sold one on the site
        result = sync_stock()
        self.assertEqual(result["updated"], 1)
        self.assertEqual(self.fake.calls[-1]["json"]["items"], [{"item_rz_id": 1001, "stock_quantity": 2}])
        self.assertEqual(self.item(1001).last_quantity, 2)

    def test_offer_gone_from_site_is_sent_as_zero(self):
        sync_stock()
        ProductAttribute.objects.filter(pk=self.small.pk).delete()
        sync_stock()
        self.assertEqual(self.fake.calls[-1]["json"]["items"], [{"item_rz_id": 1001, "stock_quantity": 0}])
        self.assertEqual(self.item(1001).last_quantity, 0)

    def test_custom_length_offer_is_zero_like_the_feed(self):
        RozetkaItem.objects.create(rz_item_id=1001, offer_id=self.offer_custom)
        RozetkaSettings.objects.filter(pk=self.cfg.pk).update(items_refreshed_at=timezone.now())
        sync_stock()
        self.assertEqual(self.fake.sent(), [{"item_rz_id": 1001, "stock_quantity": 0}])

    def test_batch_error_keeps_last_quantity(self):
        self.fake.put_reply = lambda items: FakeResponse({"success": False, "errors": {
            "message": "server_error", "code": 0, "description": "boom", "details": None}})
        result = sync_stock()
        self.assertEqual(result["updated"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("boom", result["errors"][0])
        self.assertIsNone(self.item(1001).last_quantity)
        self.assertIsNone(self.item(1002).last_quantity)

        self.fake.put_reply = None  # next pass retries
        self.assertEqual(sync_stock()["updated"], 2)

    def test_per_item_errors_skip_only_rejected_items(self):
        self.fake.put_reply = lambda items: FakeResponse({"success": False, "errors": {
            "1002": {"reason": [{"id": 1, "value": ["товар заблоковано"]}]},
        }})
        result = sync_stock()
        self.assertEqual(result["updated"], 1)
        self.assertEqual(self.item(1001).last_quantity, 3)
        self.assertIsNone(self.item(1002).last_quantity)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("1002", result["errors"][0])
        self.assertIn("товар заблоковано", result["errors"][0])

    def test_non_json_answer_is_a_batch_error(self):
        self.fake.put_reply = lambda items: FakeResponse(None, 502)
        result = sync_stock()
        self.assertEqual(result["updated"], 0)
        self.assertIn("502", result["errors"][0])

    def test_expired_token_relogin_on_mass_update(self):
        sync_stock()  # map + first push with the valid token
        ProductAttribute.objects.filter(pk=self.small.pk).update(quantity=1)
        self.fake.token = "tok-2"  # cached tok-1 is now rejected
        result = sync_stock()
        self.assertEqual(result, {"updated": 1, "errors": []})
        self.assertEqual(self.fake.calls[-1]["json"]["items"], [{"item_rz_id": 1001, "stock_quantity": 1}])
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.access_token, "tok-2")

    def test_changes_go_out_in_batches(self):
        self.fake.goods = [
            {"rz_item_id": 5000 + n, "price_offer_id": f"{900000 + n}x1"} for n in range(120)
        ]
        result = sync_stock()
        puts = [c for c in self.fake.calls if c["path"] == "/items/mass-update"]
        self.assertEqual([len(c["json"]["items"]) for c in puts], [BATCH_SIZE, BATCH_SIZE, 20])
        self.assertEqual(result["updated"], 120)
        self.assertTrue(all(i["stock_quantity"] == 0 for i in self.fake.sent()))

    def test_never_raises(self):
        class Broken:
            def iter_goods(self, **kwargs):
                raise RuntimeError("network down")

            def mass_update(self, items):
                raise RuntimeError("still down")

        RozetkaItem.objects.create(rz_item_id=1001, offer_id=self.offer_small)
        result = sync_stock(client=Broken())
        self.assertEqual(result["updated"], 0)
        self.assertEqual(len(result["errors"]), 2)
        self.assertIsNone(self.item(1001).last_quantity)

    def test_custom_client_with_per_item_errors(self):
        sent = []

        class Client:
            def iter_goods(self_inner, **kwargs):
                yield {"rz_item_id": 1001, "price_offer_id": self.offer_small}
                yield {"rz_item_id": 1002, "price_offer_id": self.offer_big}

            def mass_update(self_inner, items):
                sent.extend(items)
                return {"errors": {"1001": {"reason": [{"id": 2, "value": ["bad"]}]}}}

        result = sync_stock(client=Client())
        self.assertEqual(len(sent), 2)
        self.assertEqual(result["updated"], 1)
        self.assertIsNone(self.item(1001).last_quantity)
        self.assertEqual(self.item(1002).last_quantity, 0)


@override_settings(SITE_URL="https://mrcarpet24.com", ROZETKA_PRICE_MARKUP="1.25")
class FeedEqualityTests(TestCase):
    """The API must publish exactly what /feeds/rozetka.xml publishes."""

    @classmethod
    def setUpTestData(cls):
        _make_product(cls)  # qty 3, qty 0, custom-length
        ProductImage.objects.create(product=cls.product, image="products/gallery 1.jpg")
        size = Size.objects.create(title="1.2х1.7")
        cls.priceless = ProductAttribute.objects.create(
            product=cls.product, size=size, price=None, quantity=4, sort_order=4,
        )
        cls.many = ProductAttribute.objects.create(
            product=cls.product, size=Size.objects.create(title="2.0х3.0"),
            price=3000, quantity=250, sort_order=5,
        )
        # no usable picture: the feed drops the whole product
        cls.no_pictures = Product.objects.create(title="Килим без фото", slug="kylym-bez-foto")
        cls.hidden_attr = ProductAttribute.objects.create(
            product=cls.no_pictures, size=size, price=800, quantity=5,
        )
        other = Product.objects.create(
            title="Килим Lana", slug="kylym-lana", image="products/lana.webp",
        )
        cls.other_attr = ProductAttribute.objects.create(
            product=other, size=size, price=1200, discount=20, quantity=1,
        )

    def test_same_offers_and_quantities_as_feed(self):
        feed = {o["id"]: o["stock_quantity"] for o in build_rozetka_offers(feed_products())}
        self.assertEqual(feed_stock_quantities(), feed)
        self.assertEqual(feed[f"{self.product.pk}x{self.small.pk}"], 3)
        self.assertEqual(feed[f"{self.product.pk}x{self.big.pk}"], 0)
        self.assertEqual(feed[f"{self.product.pk}x{self.many.pk}"], 250)
        self.assertNotIn(f"{self.product.pk}x{self.priceless.pk}", feed)
        self.assertNotIn(f"{self.no_pictures.pk}x{self.hidden_attr.pk}", feed)

    def test_narrowed_query_matches_full_feed(self):
        full = feed_stock_quantities()
        narrow = feed_stock_quantities({self.product.pk})
        self.assertEqual(narrow, {k: v for k, v in full.items() if k.startswith(f"{self.product.pk}x")})

    def test_quantity_edit_shows_up_in_both(self):
        ProductAttribute.objects.filter(pk=self.small.pk).update(quantity=0)
        feed = {o["id"]: o["stock_quantity"] for o in build_rozetka_offers(feed_products())}
        self.assertEqual(feed_stock_quantities(), feed)
        self.assertEqual(feed_stock_quantities()[f"{self.product.pk}x{self.small.pk}"], 0)
