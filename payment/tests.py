from django.conf import settings
from django.test import Client, TestCase, override_settings

from cart.models import Cart
from order.models import Order
from payment.models import LiqPaySettings
from payment.utils import get_liqpay_keys


class LiqPaySettingsKeysTests(TestCase):
    @override_settings(LIQPAY_PUBLIC_KEY="env_pub", LIQPAY_PRIVATE_KEY="env_priv")
    def test_falls_back_to_env(self):
        public, private = get_liqpay_keys()
        self.assertEqual(public, "env_pub")
        self.assertEqual(private, "env_priv")

    @override_settings(LIQPAY_PUBLIC_KEY="env_pub", LIQPAY_PRIVATE_KEY="env_priv")
    def test_admin_overrides_env(self):
        LiqPaySettings.objects.create(
            public_key="admin_pub",
            private_key="admin_priv",
        )
        public, private = get_liqpay_keys()
        self.assertEqual(public, "admin_pub")
        self.assertEqual(private, "admin_priv")

    def test_singleton_add(self):
        LiqPaySettings.objects.create(public_key="a", private_key="b")
        LiqPaySettings.objects.create(public_key="c", private_key="d")
        self.assertEqual(LiqPaySettings.objects.count(), 1)


@override_settings(ALLOWED_HOSTS=["testserver"])
class PaymentStatusTests(TestCase):
    """Страховка від зависання LiqPay-віджета на кроці 3D Secure."""

    def setUp(self):
        self.client = Client()

    def _pending_order(self, status, ordered=False):
        order = Order.objects.create(
            name="Тест",
            surname="Тестовий",
            email="t@example.com",
            phone="+380000000000",
            status=status,
            total_price=100,
        )
        Cart.objects.create(order=order, ordered=ordered)
        session = self.client.session
        session["pending_payment_order_id"] = order.id
        session.save()
        return order

    def test_no_pending_order_returns_not_paid(self):
        data = self.client.get("/api/payment-status/").json()
        self.assertFalse(data["paid"])
        self.assertIsNone(data["status"])

    def test_awaiting_payment_not_paid(self):
        self._pending_order(Order.STATUS_AWAITING_PAYMENT)
        data = self.client.get("/api/payment-status/").json()
        self.assertFalse(data["paid"])
        self.assertEqual(data["status"], Order.STATUS_AWAITING_PAYMENT)

    def test_paid_order_reported(self):
        # після webhook кошик стає ordered=True — статус усе одно має знайтись
        self._pending_order(Order.STATUS_PAID, ordered=True)
        data = self.client.get("/api/payment-status/").json()
        self.assertTrue(data["paid"])
        self.assertEqual(data["status"], Order.STATUS_PAID)

    def test_shipped_counts_as_paid(self):
        self._pending_order(Order.STATUS_SHIPPED, ordered=True)
        self.assertTrue(self.client.get("/api/payment-status/").json()["paid"])

    def test_other_session_sees_nothing(self):
        self._pending_order(Order.STATUS_PAID, ordered=True)
        other = Client()  # чужа сесія — без pending_payment_order_id
        self.assertFalse(other.get("/api/payment-status/").json()["paid"])

    def test_no_cart_created_by_polling(self):
        """GET-поллінг не має плодити порожні Cart у БД (SQLite + 1 worker)."""
        before = Cart.objects.count()
        for _ in range(5):
            self.client.get("/api/payment-status/")
        self.assertEqual(Cart.objects.count(), before)

    def test_response_has_no_sensitive_fields(self):
        self._pending_order(Order.STATUS_PAID, ordered=True)
        data = self.client.get("/api/payment-status/").json()
        self.assertEqual(set(data.keys()), {"status", "paid"})
