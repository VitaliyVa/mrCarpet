"""Unit tests for GA4 ecommerce payload helpers."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from project.ga4_ecommerce import (
    cart_product_to_item,
    order_allows_purchase_event,
    purchase_payload,
)


class _FakeCategories:
    def first(self):
        return SimpleNamespace(title="Шерсть")


class Ga4EcommerceTests(TestCase):
    def test_cart_product_to_item(self):
        product = SimpleNamespace(
            pk=42,
            title="Килим Test",
            categories=_FakeCategories(),
        )
        attr = SimpleNamespace(product=product, size="160x230", custom_attribute=False)
        cp = SimpleNamespace(
            product_attr=attr,
            quantity=2,
            length=None,
            cart_product_total_price=lambda: Decimal("2000"),
        )
        item = cart_product_to_item(cp, index=1)
        self.assertEqual(item["item_id"], "42")
        self.assertEqual(item["item_name"], "Килим Test")
        self.assertEqual(item["item_category"], "Шерсть")
        self.assertEqual(item["price"], 1000.0)
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["index"], 1)

    def test_purchase_payload(self):
        product = SimpleNamespace(
            pk=1,
            title="A",
            categories=_FakeCategories(),
        )
        attr = SimpleNamespace(product=product, size="1x1", custom_attribute=False)
        cp = SimpleNamespace(
            product_attr=attr,
            quantity=1,
            length=None,
            cart_product_total_price=lambda: 500,
        )

        class _QS(list):
            def select_related(self, *a, **k):
                return self

            def prefetch_related(self, *a, **k):
                return self

        cart = SimpleNamespace(
            cart_products=SimpleNamespace(
                select_related=lambda *a, **k: SimpleNamespace(
                    prefetch_related=lambda *a2, **k2: _QS([cp])
                )
            ),
            get_total_price=lambda: 500,
        )
        order = SimpleNamespace(order_number=123456, payment_type="cash")
        payload = purchase_payload(order, cart)
        self.assertEqual(payload["transaction_id"], "123456")
        self.assertEqual(payload["currency"], "UAH")
        self.assertEqual(payload["value"], 500.0)
        self.assertEqual(len(payload["items"]), 1)

    def test_order_allows_purchase_event(self):
        self.assertTrue(
            order_allows_purchase_event(SimpleNamespace(status="new"))
        )
        self.assertTrue(
            order_allows_purchase_event(SimpleNamespace(status="paid"))
        )
        self.assertFalse(
            order_allows_purchase_event(
                SimpleNamespace(status="awaiting_payment")
            )
        )
        self.assertFalse(
            order_allows_purchase_event(SimpleNamespace(status="cancelled"))
        )
        self.assertFalse(order_allows_purchase_event(None))
