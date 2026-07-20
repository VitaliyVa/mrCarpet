"""Tests: кошик не створюється на перегляді + очищення покинутих."""

from datetime import timedelta

from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from cart.management.commands.cleanup_carts import cleanup_carts
from cart.models import Cart, CartProduct
from cart.utils import EmptyCart, get_cart, get_cart_readonly
from catalog.models import Product, ProductAttribute
from order.models import Order
from users.models import CustomUser


class ReadonlyCartTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, session=None):
        request = self.factory.get("/")
        request.session = session if session is not None else {}
        request.user = type("Anon", (), {"is_authenticated": False})()
        return request

    def test_anonymous_view_creates_no_cart(self):
        before = Cart.objects.count()
        cart = get_cart_readonly(self._request())
        self.assertIsInstance(cart, EmptyCart)
        self.assertEqual(Cart.objects.count(), before)

    def test_empty_cart_is_falsy_and_safe(self):
        cart = EmptyCart()
        self.assertFalse(bool(cart))
        self.assertEqual(cart.get_total_price(), 0)
        self.assertEqual(cart.get_cart_product_total_quantity(), 0)
        self.assertEqual(list(cart.cart_products.all()), [])

    def test_existing_session_cart_is_found(self):
        cart = Cart.objects.create()
        found = get_cart_readonly(self._request(session={"cart_id": cart.id}))
        self.assertEqual(found.pk, cart.pk)

    def test_stale_session_id_returns_empty(self):
        before = Cart.objects.count()
        found = get_cart_readonly(self._request(session={"cart_id": 999999}))
        self.assertIsInstance(found, EmptyCart)
        self.assertEqual(Cart.objects.count(), before)

    def test_get_cart_still_creates_for_real_actions(self):
        request = self._request(session={})
        before = Cart.objects.count()
        cart = get_cart(request)
        self.assertEqual(Cart.objects.count(), before + 1)
        self.assertIsNotNone(cart.pk)


@override_settings(ALLOWED_HOSTS=["testserver"])
class PageViewDoesNotCreateCartTests(TestCase):
    def test_homepage_visit_creates_no_cart(self):
        before = Cart.objects.count()
        resp = Client().get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Cart.objects.count(), before)

    def test_many_bot_visits_create_nothing(self):
        before = Cart.objects.count()
        for _ in range(5):
            Client().get("/")  # кожен «бот» без cookie
        self.assertEqual(Cart.objects.count(), before)


class CleanupCartsTests(TestCase):
    def _age(self, cart, days):
        Cart.objects.filter(pk=cart.pk).update(
            updated=timezone.now() - timedelta(days=days)
        )

    def _cart_with_product(self):
        product = Product.objects.create(title="Килим")
        attr = ProductAttribute.objects.create(
            product=product, price=100, quantity=5
        )
        cart = Cart.objects.create()
        CartProduct.objects.create(cart=cart, product_attr=attr, quantity=1)
        return cart

    def test_deletes_old_empty_anonymous(self):
        cart = Cart.objects.create()
        self._age(cart, 10)
        result = cleanup_carts(empty_days=7)
        self.assertEqual(result["empty_deleted"], 1)
        self.assertFalse(Cart.objects.filter(pk=cart.pk).exists())

    def test_keeps_fresh_empty(self):
        cart = Cart.objects.create()
        cleanup_carts(empty_days=7)
        self.assertTrue(Cart.objects.filter(pk=cart.pk).exists())

    def test_keeps_cart_with_order(self):
        order = Order.objects.create(
            name="N",
            surname="S",
            email="e@e.com",
            phone="+380000000000",
            total_price=100,
        )
        cart = Cart.objects.create(order=order)
        self._age(cart, 400)
        cleanup_carts(empty_days=1, abandoned_days=1)
        self.assertTrue(Cart.objects.filter(pk=cart.pk).exists())

    def test_keeps_ordered_cart(self):
        cart = Cart.objects.create(ordered=True)
        self._age(cart, 400)
        cleanup_carts(empty_days=1, abandoned_days=1)
        self.assertTrue(Cart.objects.filter(pk=cart.pk).exists())

    def test_keeps_user_cart(self):
        user = CustomUser.objects.create_user(email="u@e.com", password="x")
        cart = Cart.objects.create(user=user)
        self._age(cart, 400)
        cleanup_carts(empty_days=1, abandoned_days=1)
        self.assertTrue(Cart.objects.filter(pk=cart.pk).exists())

    def test_keeps_recent_cart_with_items(self):
        cart = self._cart_with_product()
        self._age(cart, 10)
        cleanup_carts(empty_days=7, abandoned_days=90)
        self.assertTrue(Cart.objects.filter(pk=cart.pk).exists())

    def test_deletes_long_abandoned_with_items(self):
        cart = self._cart_with_product()
        self._age(cart, 120)
        result = cleanup_carts(empty_days=7, abandoned_days=90)
        self.assertEqual(result["abandoned_deleted"], 1)
        self.assertFalse(Cart.objects.filter(pk=cart.pk).exists())

    def test_dry_run_changes_nothing(self):
        cart = Cart.objects.create()
        self._age(cart, 30)
        result = cleanup_carts(empty_days=7, dry_run=True)
        self.assertEqual(result["empty_deleted"], 1)
        self.assertTrue(Cart.objects.filter(pk=cart.pk).exists())
