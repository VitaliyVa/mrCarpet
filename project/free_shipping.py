"""Безкоштовна доставка — єдине джерело правди для UI / order / SEO."""

from __future__ import annotations


def get_shop_settings():
    from .models import ShopSettings

    return ShopSettings.load()


def free_shipping_for_total(cart_total) -> dict:
    """
    Стан безкоштовної доставки для суми товарів (після промокоду).

    Не змінює total_price замовлення — доставка лишається у перевізника,
    магазин компенсує операційно коли qualifies=True.
    """
    settings = get_shop_settings()
    try:
        total = float(cart_total or 0)
    except (TypeError, ValueError):
        total = 0.0

    enabled = bool(settings.free_shipping_enabled)
    threshold = int(settings.free_shipping_threshold or 0)
    from_price = int(settings.delivery_from_price or 0)
    qualifies = enabled and threshold > 0 and total >= threshold
    remaining = max(0, threshold - int(round(total))) if enabled and not qualifies else 0

    return {
        "enabled": enabled,
        "threshold": threshold,
        "delivery_from_price": from_price,
        "qualifies": qualifies,
        "remaining": remaining,
        "promo_label": (
            f"Безкоштовна доставка від {threshold} грн." if enabled else ""
        ),
    }
