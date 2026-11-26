"""GA4 ecommerce payloads from cart / order (server-side)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from project.merchant_feed import offer_id

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
        # Same id as the Merchant feed g:id, so Ads cart data can join it.
        "item_id": offer_id(product, attr),
        "item_group_id": str(product.pk),
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
    # What the buyer pays (after promocode), not the cart list price: this
    # value is what tROAS bidding learns from.
    total = getattr(order, "total_price", None)
    if total:
        payload["value"] = round(_money(total), 2)
    payload["shipping"] = 0
    # Custom param (not in GA4 purchase schema) — kept for reports/debug.
    if getattr(order, "payment_type", None):
        payload["payment_type"] = order.payment_type
    return payload


def order_allows_purchase_event(order) -> bool:
    """True when GA4 purchase may fire for this order."""
    if order is None:
        return False
    # Marketplace orders (Rozetka) are not our site's conversions: reporting
    # them would feed Google Ads purchases that never came from its clicks.
    if getattr(order, "source", "site") != "site":
        return False
    status = getattr(order, "status", None)
    return status in PURCHASE_ELIGIBLE_STATUSES


# Cash on delivery is money in hand only once the parcel is picked up
# ("completed") or the cash transfer arrived and the manager set "paid".
# "shipped" is not a sale yet: refused parcels come back from that status.
COD_DELIVERED_STATUSES = frozenset({"paid", "completed"})
# Card orders are paid before they move past awaiting_payment.
PREPAID_SALE_STATUSES = frozenset({"paid", "shipped", "completed"})


def cod_purchase_stage() -> str:
    """"delivery" (default) or "order", see settings.ADS_COD_PURCHASE_STAGE."""
    from django.conf import settings

    stage = str(getattr(settings, "ADS_COD_PURCHASE_STAGE", "delivery") or "")
    return "order" if stage.strip().lower() == "order" else "delivery"


def order_is_real_sale(order) -> bool:
    """True when the order is money the shop really got (or will, card).

    Used for the offline conversion export, independent of the GA4 stage
    setting: Ads offline uploads should only ever carry real sales.
    """
    if order is None or getattr(order, "source", "site") != "site":
        return False
    status = getattr(order, "status", None)
    if getattr(order, "payment_type", None) == "cash":
        return status in COD_DELIVERED_STATUSES
    return status in PREPAID_SALE_STATUSES


def order_purchase_is_due(order) -> bool:
    """True when the GA4 `purchase` for this order should be sent now."""
    if not order_allows_purchase_event(order):
        return False
    if getattr(order, "payment_type", None) != "cash":
        return True
    if cod_purchase_stage() == "order":
        return True
    return getattr(order, "status", None) in COD_DELIVERED_STATUSES
