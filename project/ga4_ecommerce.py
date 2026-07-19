"""GA4 ecommerce payloads from cart / order (server-side)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# Statuses where client may emit `purchase` (not unpaid / cancelled).
PURCHASE_ELIGIBLE_STATUSES = frozenset(
    {
        "new",  # cash on delivery
        "paid",
        "shipped",
        "completed",
    }
)


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def cart_product_to_item(cart_product, index: int = 0) -> dict:
    attr = cart_product.product_attr
    product = attr.product
    category = product.categories.first()
    line_total = cart_product.cart_product_total_price() or 0
    qty = int(cart_product.quantity or 1)
    if qty < 1:
        qty = 1
    unit = _money(line_total) / qty
    variant = ""
    if getattr(attr, "size", None):
        variant = str(attr.size)
    elif getattr(cart_product, "length", None):
        variant = f"{cart_product.length}м"

    return {
        "item_id": str(product.pk),
        "item_name": product.title or "",
        "item_brand": "mr.Carpet",
        "item_category": category.title if category else "",
        "item_variant": variant,
        "price": round(unit, 2),
        "quantity": qty,
        "index": index,
    }


def cart_ecommerce_payload(cart) -> dict:
    products = list(
        cart.cart_products.select_related(
            "product_attr",
            "product_attr__product",
            "product_attr__size",
        ).prefetch_related("product_attr__product__categories")
    )
    items = [cart_product_to_item(cp, i) for i, cp in enumerate(products)]
    return {
        "currency": "UAH",
        "value": round(_money(cart.get_total_price()), 2),
        "items": items,
    }


def purchase_payload(order, cart) -> dict:
    payload = cart_ecommerce_payload(cart)
    payload["transaction_id"] = str(order.order_number)
    payload["shipping"] = 0
    # Custom param (not in GA4 purchase schema) — kept for reports/debug.
    if getattr(order, "payment_type", None):
        payload["payment_type"] = order.payment_type
    return payload


def order_allows_purchase_event(order) -> bool:
    """True when GA4 purchase may fire for this order."""
    if order is None:
        return False
    status = getattr(order, "status", None)
    return status in PURCHASE_ELIGIBLE_STATUSES
