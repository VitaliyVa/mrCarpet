from .models import Cart
from .utils import get_cart


def context(request):
    cart = get_cart(request)
    cart_products = cart.cart_products.all()
    context = {
        'cart': cart,
        'cart_products': cart_products
    }
    print(len(cart_products))
    return context