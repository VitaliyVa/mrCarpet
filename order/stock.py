"""Give an order's stock back when it is cancelled, and take it again if the
cancel is undone. Exactly once each way, tracked by Order.stock_returned.

Checkout (Cart.apply_quantity) and the Rozetka import take stock when the
order is created. Before this module only a cancel that came from Rozetka
itself gave it back, so a site order cancelled in the admin left the rug
«Немає в наявності» while it sat on the shelf.

Cut-to-length lines are skipped both ways: apply_quantity shrinks max_len and
clamps it at min_len, so the exact amount taken is not recoverable, and
ProductAttribute.save() on a custom attribute deletes its cart lines. Only
queryset .update() touches ProductAttribute here, for the same reason.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import F

logger = logging.getLogger(__name__)


def _units(order, cart_products) -> dict:
    """{product_attr_id: units} this order took from stock."""
    from order.models import Order

    if order.source == Order.SOURCE_ROZETKA:
        from project.rozetka_orders import _stock_to_return

        per_line = _stock_to_return(order, cart_products)
    else:
        per_line = {
            cp.pk: int(cp.quantity or 0)
            for cp in cart_products
            if not cp.product_attr.custom_attribute and int(cp.quantity or 0) > 0
        }
    result: dict = {}
    for cp in cart_products:
        units = per_line.get(cp.pk)
        if units:
            result[cp.product_attr_id] = result.get(cp.product_attr_id, 0) + units
    return result


def return_stock(order_pk: int) -> int:
    """Put a cancelled order's units back. Returns units returned (0 if done)."""
    from cart.models import CartProduct
    from catalog.models import ProductAttribute
    from order.models import Order

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_pk).first()
        if order is None or order.stock_returned or order.status != Order.STATUS_CANCELLED:
            return 0
        lines = list(
            CartProduct.objects.filter(cart__order=order)
            .select_related("product_attr__product")
            .order_by("pk")
        )
        units = _units(order, lines)
        for attr_id, count in units.items():
            ProductAttribute.objects.filter(pk=attr_id).update(quantity=F("quantity") + count)
        Order.objects.filter(pk=order.pk).update(stock_returned=True)
    total = sum(units.values())
    logger.info("order %s cancelled: %s units back to stock", order_pk, total)
    return total


def take_stock_again(order_pk: int) -> int:
    """A cancel was undone: take the returned units again (never below zero)."""
    from cart.models import CartProduct
    from catalog.models import ProductAttribute
    from order.models import Order

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_pk).first()
        if order is None or not order.stock_returned or order.status == Order.STATUS_CANCELLED:
            return 0
        lines = list(
            CartProduct.objects.filter(cart__order=order)
            .select_related("product_attr__product")
            .order_by("pk")
        )
        units = _units(order, lines)
        taken = 0
        for attr_id, count in units.items():
            attr = ProductAttribute.objects.select_for_update().filter(pk=attr_id).first()
            if attr is None:
                continue
            take = min(int(attr.quantity or 0), count)
            ProductAttribute.objects.filter(pk=attr_id).update(quantity=F("quantity") - take)
            taken += take
        Order.objects.filter(pk=order.pk).update(stock_returned=False)
    return taken


def returnable_units(order) -> int:
    """How many units a cancel would give back now (for the bot's preview)."""
    from cart.models import CartProduct

    if order.stock_returned:
        return 0
    lines = list(
        CartProduct.objects.filter(cart__order=order).select_related("product_attr__product")
    )
    return sum(_units(order, lines).values())
