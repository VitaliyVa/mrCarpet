from project.free_shipping import free_shipping_for_total, get_shop_settings

from .utils import get_cart


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
    cart = get_cart(request)
    cart_products = cart.cart_products.all()
    try:
        fs = free_shipping_for_total(cart.get_total_price())
    except Exception:
        fs = _fallback_free_shipping()
    return {
        "cart": cart,
        "cart_products": cart_products,
        "free_shipping": fs,
    }
