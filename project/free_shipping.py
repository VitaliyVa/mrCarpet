"""Безкоштовна доставка — єдине джерело правди для UI / order / SEO.

Delivery and return terms live here too, so the delivery page, the PDP buy
box, checkout, JSON-LD shippingDetails / MerchantReturnPolicy and the Merchant
feed all state the same numbers. Merchant Center compares them with each
other: a page saying "paid by the buyer" next to markup saying "0 UAH" is a
misrepresentation risk.
"""

from __future__ import annotations

# Nova Poshta is the only carrier offered at checkout.
SHIPPING_CARRIER = "Нова Пошта"
SHIPPING_COUNTRY = "UA"
# Business days before the parcel is handed to the carrier (0 = same day).
HANDLING_DAYS = (0, 2)
# Days the parcel travels with the carrier.
TRANSIT_DAYS = (1, 5)
# Consumer return window, days (the /refund/ page states the same).
RETURN_DAYS = 14

_DAY_FORMS = ("день", "дні", "днів")
_WORKDAY_GEN_FORMS = ("робочого дня", "робочих днів", "робочих днів")


def get_shop_settings():
    from .models import ShopSettings

    return ShopSettings.load()


def _plural(n: int, forms) -> str:
    from catalog.templatetags.catalog_filters import plural_uk_form

    return plural_uk_form(n, forms)


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


def shipping_rate(price=None, settings=None) -> int | None:
    """Delivery price (UAH) the buyer pays for goods worth `price`.

    0 from the free threshold, else the carrier "from" tariff shown at
    checkout. `price=None` means "the store in general": free when free
    shipping is on. None when there is no tariff to state.
    """
    if settings is None:
        settings = get_shop_settings()
    threshold = int(settings.free_shipping_threshold or 0)
    free = bool(settings.free_shipping_enabled) and (
        price is None or (threshold > 0 and float(price) >= threshold)
    )
    if free:
        return 0
    return int(settings.delivery_from_price or 0) or None


def delivery_terms(settings=None) -> dict:
    """Delivery / return facts for templates (`shop_terms` in context)."""
    if settings is None:
        settings = get_shop_settings()
    enabled = bool(settings.free_shipping_enabled)
    threshold = int(settings.free_shipping_threshold or 0)
    t_min, t_max = TRANSIT_DAYS
    h_max = HANDLING_DAYS[1]
    return {
        "carrier": SHIPPING_CARRIER,
        "free_enabled": enabled and threshold > 0,
        "threshold": threshold,
        "from_price": int(settings.delivery_from_price or 0),
        "handling_max": h_max,
        "transit_min": t_min,
        "transit_max": t_max,
        # "1-5 днів"
        "transit_text": f"{t_min}-{t_max} {_plural(t_max, _DAY_FORMS)}",
        # "до 2 робочих днів"
        "handling_text": f"до {h_max} {_plural(h_max, _WORKDAY_GEN_FORMS)}",
        "return_days": RETURN_DAYS,
        "return_days_text": f"{RETURN_DAYS} {_plural(RETURN_DAYS, _DAY_FORMS)}",
    }
