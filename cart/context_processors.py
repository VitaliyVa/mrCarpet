from project.free_shipping import free_shipping_for_total, get_shop_settings
from project.ga4_ecommerce import cart_ecommerce_payload

from .utils import get_cart_readonly


def _fallback_free_shipping():
    """Без фейкового порогу 800 — беремо актуальні ShopSettings або «вимкнено»."""
    try:
        settings = get_shop_settings()
        threshold = int(settings.free_shipping_threshold or 0)
        return {
            "enabled": bool(settings.free_shipping_enabled),
            "threshold": threshold,
            "delivery_from_price": int(settings.delivery_from_price or 0),
            "qualifies": False,
            "remaining": threshold if settings.free_shipping_enabled else 0,
            "promo_label": (
                f"Безкоштовна доставка від {threshold} грн."
                if settings.free_shipping_enabled and threshold
                else ""
            ),
        }
    except Exception:
        return {
            "enabled": False,
            "threshold": 0,
            "delivery_from_price": 0,
            "qualifies": False,
            "remaining": 0,
            "promo_label": "",
        }


def context(request):
    # Тільки читаємо: рендер сторінки не має створювати кошик у БД
    cart = get_cart_readonly(request)
    cart_products = cart.cart_products.all()
    try:
        fs = free_shipping_for_total(cart.get_total_price())
    except Exception:
        fs = _fallback_free_shipping()
    # Only build GA payload when cart has lines (bool(qs) → EXISTS).
    ga4_cart = None
    if cart_products:
        try:
            ga4_cart = cart_ecommerce_payload(cart)
        except Exception:
            ga4_cart = None

    return {
        "cart": cart,
        "cart_products": cart_products,
        "free_shipping": fs,
        "ga4_cart": ga4_cart,
    }
