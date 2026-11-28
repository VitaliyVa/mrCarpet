from unittest.mock import patch

from django.test import TestCase, override_settings

from cart.models import Cart, CartProduct
from catalog.models import Product, ProductAttribute, Size
from order.customer_contact import (
    call_script,
    customer_message,
    handle_order_callback,
    is_mobile,
    normalize_phone,
    order_checks,
    order_keyboard,
    viber_link_token,
)
from order.models import Order
from project.models import TelegramSettings
from project.telegram_utils import format_order_message

BRANCH = "Відділення №104 (до 30 кг на одне місце): вул. Карла Мікльоша, 19"


class PhoneTests(TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_phone("+380 73 209 59 12"), "380732095912")
        self.assertEqual(normalize_phone("073 209 5912"), "380732095912")
        self.assertEqual(normalize_phone("12345"), "")
        self.assertTrue(is_mobile("+380 97 606 34 09"))
        self.assertFalse(is_mobile("+380 44 123 45 67"))  # Kyiv landline


class _Fixture:
    def _order(self, *, title="Килим овальний сірий Fantasy Grey 12500.16 O",
                size="1.0х2.0", stock=0, address=BRANCH, phone="+380 73 209 59 12",
                **extra):
        product = Product.objects.create(title=title, slug=f"p-{Product.objects.count()}")
        attr = ProductAttribute.objects.create(
            product=product, size=Size.objects.create(title=size), price=1400, quantity=stock
        )
        fields = dict(
            order_number=5252854628389 + Order.objects.count(),
            name="Тетяна", surname="Пуняк", phone=phone, city="Львів",
            address=address, payment_type=Order.PAYMENT_CASH, total_price=1400,
        )
        fields.update(extra)
        order = Order.objects.create(**fields)
        cart = Cart.objects.create(order=order)
        CartProduct.objects.create(cart=cart, product_attr=attr, quantity=1)
        return order


class OrderChecksTests(_Fixture, TestCase):
    def test_parcel_and_last_item(self):
        checks = order_checks(self._order())
        self.assertTrue(any(c.startswith("📦 Посилка: ~4.8 кг") for c in checks), checks)
        self.assertTrue(any("Останній на складі" in c for c in checks))
        self.assertFalse(any(c.startswith("⚠️") for c in checks), checks)

    def test_post_box_and_long_roll(self):
        box = order_checks(self._order(address="Поштомат \"Нова Пошта\" №5512: вул. Шевченка, 1"))
        self.assertTrue(any("Поштомат" in c for c in box), box)
        big = order_checks(self._order(size="2.0х3.0"))
        self.assertTrue(any("можуть не прийняти" in c for c in big), big)

    def test_bad_phone_repeat_and_history(self):
        first = self._order(status=Order.STATUS_CANCELLED)
        second = self._order(phone="0732095912")
        checks = order_checks(second)
        self.assertTrue(any("скасовано замовлень: 1" in c for c in checks), checks)
        self.assertFalse(any("дубль" in c for c in checks))  # cancelled one is not a dupe
        third = self._order(phone="+380732095912")
        self.assertTrue(any(f"№{second.order_number}" in c for c in order_checks(third)))
        self.assertTrue(any("неправильний" in c for c in order_checks(self._order(phone="+380 44 1"))))
        self.assertIsNotNone(first)

    def test_rozetka_unpaid(self):
        checks = order_checks(self._order(payment_type=Order.PAYMENT_ROZETKA_UNPAID, source="rozetka"))
        self.assertIn("⚠️ Rozetka: ще не оплачено, не відправляти", checks)

    def test_checks_in_notification(self):
        text = format_order_message(self._order())
        self.assertIn("Перевірки:", text)
        self.assertIn("📦 Посилка", text)


class TextsTests(_Fixture, TestCase):
    def test_customer_message(self):
        text = customer_message(self._order())
        self.assertIn("Добрий день, Тетяна!", text)
        self.assertIn("Fantasy Grey 12500.16 O, 100x200 см, 1 шт.", text)
        self.assertIn("💰 1400 грн, оплата при отриманні", text)
        self.assertIn("🚚 Нова Пошта: Львів, Відділення №104: вул. Карла Мікльоша, 19", text)
        self.assertIn("✅", text)
        self.assertIn("за тарифом Нової Пошти", text)
        self.assertNotIn("—", text)

    def test_call_script(self):
        order = self._order(address="Поштомат №1: вул. Шевченка, 1")
        text = call_script(order)
        self.assertIn("розмір 1 на 2 м", text)
        self.assertIn("Уточнити під час дзвінка:", text)
        self.assertIn("Поштомат", text)
        self.assertNotIn("—", text)


@override_settings(SITE_URL="https://mrcarpet24.com")
class CallbackTests(_Fixture, TestCase):
    def setUp(self):
        TelegramSettings.objects.update_or_create(
            pk=1, defaults={"bot_token": "t", "chat_id": "-100", "is_enabled": True}
        )

    def _cq(self, data, chat=-100):
        return {"id": "1", "data": data,
                "message": {"message_id": 7, "chat": {"id": chat}}}

    @patch("project.telegram_api.answer_callback_query")
    @patch("project.telegram_api.send_message")
    def test_message_button(self, send, answer):
        order = self._order()
        self.assertTrue(handle_order_callback(self._cq(order_keyboard(order)["inline_keyboard"][0][0]["callback_data"])))
        text = send.call_args.args[0]
        self.assertIn("<pre>Добрий день, Тетяна!", text)
        buttons = send.call_args.kwargs["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([b["text"] for b in buttons], ["Viber", "Telegram", "WhatsApp"])
        self.assertEqual(buttons[2]["url"], "https://wa.me/380732095912")

    @patch("project.telegram_api.answer_callback_query")
    @patch("project.telegram_api.send_message")
    def test_call_button_and_foreign_chat(self, send, answer):
        order = self._order()
        self.assertTrue(handle_order_callback(self._cq(f"ordcl:{order.pk}")))
        self.assertIn("Це магазин килимів mr.Carpet", send.call_args.args[0])
        send.reset_mock()
        self.assertTrue(handle_order_callback(self._cq(f"ordcl:{order.pk}", chat=5)))
        send.assert_not_called()
        self.assertFalse(handle_order_callback(self._cq("crok:1")))

    def test_viber_page(self):
        order = self._order()
        response = self.client.get(f"/api/order-viber/{viber_link_token(order)}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "viber://chat?number=%2B380732095912")
        self.assertEqual(self.client.get("/api/order-viber/bad:token/").status_code, 404)


class FreeShippingHintTests(_Fixture, TestCase):
    @patch("order.customer_contact._shop_threshold", return_value=1499)
    def test_threshold_and_gap(self, _):
        text = customer_message(self._order(total_price=1400))
        self.assertIn("🎁 У нас безкоштовна доставка від 1499 грн", text)
        self.assertIn("не вистачило лише 99 грн", text)
        far = customer_message(self._order(total_price=400))
        self.assertIn("🎁 У нас безкоштовна доставка від 1499 грн", far)
        self.assertNotIn("не вистачило", far)
        free = customer_message(self._order(total_price=2000, free_shipping=True))
        self.assertIn("📦 Доставка для вас безкоштовна", free)
        self.assertNotIn("від 1499", free)
