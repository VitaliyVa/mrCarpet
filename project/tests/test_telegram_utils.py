from django.test import TestCase, override_settings

from order.models import Order
from project.telegram_utils import format_order_message, order_admin_absolute_url


class OrderNotifyLinkTests(TestCase):
    @override_settings(SITE_URL="https://mrcarpet24.com")
    def test_admin_link_in_order_message(self):
        order = Order.objects.create(
            order_number=9106492351856,
            name="Vitaliy",
            surname="St",
            phone="+380964042174",
            email="vistet1428@gmail.com",
            status=Order.STATUS_PAID,
            payment_type=Order.PAYMENT_LIQPAY,
            total_price=1000,
            city="Ланівці",
            address="Відділення №1: вул. Незалежності, 10",
        )
        url = order_admin_absolute_url(order)
        self.assertEqual(
            url, f"https://mrcarpet24.com/admin/order/order/{order.pk}/change/"
        )
        html = format_order_message(order, event="paid")
        self.assertIn(f'href="{url}"', html)
        self.assertIn("Відкрити в адмінці", html)
        self.assertIn("Місто: Ланівці", html)
        self.assertIn("Відділення НП: Відділення №1", html)
