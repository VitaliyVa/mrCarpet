from .models import Cart


def get_cart(request) -> Cart:
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user, ordered=False)
        except:
            cart = Cart.objects.create(user=request.user)
    else:
        try:
            cart_id = request.session.get("cart_id")
            cart = Cart.objects.get(id=cart_id, ordered=False)
        except:
            cart = Cart.objects.create()
            request.session["cart_id"] = cart.id
    return cart