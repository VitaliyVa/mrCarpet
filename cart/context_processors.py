from project.free_shipping import free_shipping_for_total

from .utils import get_cart


def context(request):
    cart = get_cart(request)
    cart_products = cart.cart_products.all()
    print(len(cart_products))
    try:
        fs = free_shipping_for_total(cart.get_total_price())
    except Exception:
        fs = {
            "enabled": False,
            "threshold": 800,
            "delivery_from_price": 90,
            "qualifies": False,
            "remaining": 0,
            "promo_label": "",
        }
    return {
        "cart": cart,
        "cart_products": cart_products,
        "free_shipping": fs,
    }