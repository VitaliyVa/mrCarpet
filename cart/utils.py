from .models import Cart


class EmptyCart:
    """Кошик-заглушка для відвідувача, який ще нічого не додав.

    Потрібна, щоб не створювати рядок у БД на кожен перегляд сторінки:
    context processor смикається на КОЖНОМУ запиті, тож кожен бот/сканер
    без cookie інакше плодить порожній Cart (+ запис у SQLite, а це наш
    вузький ресурс). Реальний кошик створює get_cart() — при першій
    справжній дії (додати товар, чекаут, промокод).
    """

    pk = None
    id = None
    ordered = False
    order = None
    order_id = None
    user = None
    user_id = None
    promocode = None
    promocode_id = None

    @property
    def cart_products(self):
        from .models import CartProduct

        return CartProduct.objects.none()

    def get_total_price(self, *args, **kwargs):
        return 0

    def get_cart_product_total_quantity(self) -> int:
        return 0

    def __bool__(self) -> bool:
        # {% if cart %} у шаблонах має поводитись як «кошика ще немає»
        return False


def get_cart_readonly(request):
    """Знайти кошик, НЕ створюючи його. Ніколи не пише в БД."""
    if getattr(request, "user", None) and request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user, ordered=False).first()
        return cart or EmptyCart()
    session = getattr(request, "session", None)
    cart_id = session.get("cart_id") if session else None
    if not cart_id:
        return EmptyCart()
    cart = Cart.objects.filter(id=cart_id, ordered=False).first()
    return cart or EmptyCart()


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


def cart_total_price(cart):
    total_price = sum([cp.cart_product_total_price() or 0 for cp in cart.cart_products.all()])
    return total_price
