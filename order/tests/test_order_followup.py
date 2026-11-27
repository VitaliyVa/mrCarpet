from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import ProductAttribute
from order import bot_status, shipping
from order.models import Order
from order.tests.test_customer_contact import _Fixture
from project.models import TelegramSettings

KYIV = ZoneInfo("Europe/Kyiv")


def _attr(order):
    return ProductAttribute.objects.get(cart_products__cart__order=order)


class StockOnCancelTests(_Fixture, TestCase):
    def test_cancel_returns_once_and_uncancel_takes_again(self):
        order = self._order(stock=0)
        order.status = Order.STATUS_CANCELLED
        order.save()
        self.assertEqual(_attr(order).quantity, 1)
        order.refresh_from_db()
        self.assertTrue(order.stock_returned)
        order.message = "edit"
        order.save()  # still cancelled: no second return
        self.assertEqual(_attr(order).quantity, 1)
        order.status = Order.STATUS_NEW
        order.save()
        self.assertEqual(_attr(order).quantity, 0)
        order.refresh_from_db()
        self.assertFalse(order.stock_returned)

    def test_rozetka_cancel_from_poller_not_doubled(self):
        from project.rozetka_orders import cancel_order

        order = self._order(stock=0, source=Order.SOURCE_ROZETKA, rozetka_order_id=777)
        cancel_order(777)
        self.assertEqual(_attr(order).quantity, 1)


class ShippedEmailTests(_Fixture, TestCase):
    def test_normalize_ttn(self):
        self.assertEqual(shipping.normalize_ttn("20 4500 1234 5678"), "20450012345678")
        self.assertEqual(shipping.normalize_ttn("123"), "")

    @patch("order.shipping.enqueue_shipped_email")
    def test_signal_once_per_ttn(self, enqueue):
        order = self._order(email="buyer@example.com")
        order.status = Order.STATUS_SHIPPED
        order.save()
        enqueue.assert_not_called()  # no TTN yet
        order.ttn = "20450012345678"
        order.save()
        enqueue.assert_called_once_with(order.pk)

    @patch("project.smtp_utils.send_smtp_mail", return_value=True)
    def test_send_marks_once(self, send):
        order = self._order(email="buyer@example.com")
        Order.objects.filter(pk=order.pk).update(status=Order.STATUS_SHIPPED, ttn="20450012345678")
        self.assertTrue(shipping.send_shipped_email(order.pk))
        subject, body = send.call_args.args[0], send.call_args.args[1]
        self.assertIn("вже в дорозі", subject)
        self.assertIn("20450012345678", body)
        self.assertIn("novaposhta.ua/tracking/?cargo_number=20450012345678", body)
        self.assertFalse(shipping.send_shipped_email(order.pk))
        self.assertEqual(send.call_count, 1)


@override_settings(SITE_URL="https://mrcarpet24.com")
class BotStatusTests(_Fixture, TestCase):
    def setUp(self):
        TelegramSettings.objects.update_or_create(
            pk=1, defaults={"bot_token": "t", "chat_id": "-100", "is_enabled": True}
        )

    def _cq(self, data, markup=None):
        msg = {"message_id": 7, "chat": {"id": -100}, "text": "x"}
        if markup:
            msg["reply_markup"] = markup
        return {"id": "1", "data": data, "message": msg}

    def test_menu_and_preview(self):
        order = self._order(stock=0)
        text, markup = bot_status.menu(order)
        labels = [b["text"] for row in markup["inline_keyboard"] for b in row]
        self.assertIn("Зараз: «Нове»", text)
        self.assertNotIn("Нове", labels)
        self.assertIn("Відправлено", labels)
        preview, _ = bot_status.preview(order, Order.STATUS_CANCELLED)
        self.assertIn("Килим повернеться на склад: 1 шт.", preview)
        shipped, _ = bot_status.preview(order, Order.STATUS_SHIPPED)
        self.assertIn("Email немає: дам текст з ТТН для Viber", shipped)

    def test_rozetka_cancel_asks_reason(self):
        order = self._order(source=Order.SOURCE_ROZETKA, rozetka_order_id=5)
        _, markup = bot_status.preview(order, Order.STATUS_CANCELLED)
        data = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        self.assertIn(f"ordok:{order.pk}:x:42", data)
        self.assertFalse(bot_status.apply_status(order.pk, Order.STATUS_CANCELLED)[0])

    @patch("project.telegram_api.answer_callback_query")
    @patch("project.telegram_api.edit_message_text")
    @patch("project.telegram_api.send_message")
    def test_cancel_via_buttons(self, send, edit, answer):
        from order.customer_contact import handle_order_callback, order_keyboard

        order = self._order(stock=0)
        card = order_keyboard(order)
        self.assertTrue(handle_order_callback(self._cq(f"ordst:{order.pk}", card)))
        send.assert_called_once()  # menu opened under the card, card kept
        edit.assert_not_called()
        self.assertTrue(handle_order_callback(self._cq(f"ordok:{order.pk}:x")))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(_attr(order).quantity, 1)
        self.assertIn("Килим повернено на склад", edit.call_args.args[2])

    @patch("order.shipping.enqueue_shipped_email")
    @patch("project.telegram_api.send_message")
    def test_ttn_reply(self, send, enqueue):
        order = self._order()
        prompt = bot_status.ttn_prompt(order)
        msg = {"message_id": 9, "chat": {"id": -100}, "text": "2045 0012 3456 78",
               "reply_to_message": {"text": prompt}}
        self.assertTrue(bot_status.handle_ttn_reply(msg))
        order.refresh_from_db()
        self.assertEqual((order.status, order.ttn), (Order.STATUS_SHIPPED, "20450012345678"))
        texts = " ".join(c.args[0] for c in send.call_args_list)
        self.assertIn("«Нове» → «Відправлено»", texts)
        self.assertIn("<pre>Добрий день, Тетяна!", texts)  # no email: Viber text
        bad = dict(msg, text="12345")
        send.reset_mock()
        self.assertTrue(bot_status.handle_ttn_reply(bad))
        self.assertIn("14 цифр", send.call_args.args[0])
        self.assertFalse(bot_status.handle_ttn_reply({"chat": {"id": -100}, "text": "hi",
                                                       "reply_to_message": {"text": "other"}}))


class TrackingTests(_Fixture, TestCase):
    def setUp(self):
        TelegramSettings.objects.update_or_create(
            pk=1, defaults={"bot_token": "t", "chat_id": "-100", "is_enabled": True}
        )

    def _shipped(self):
        order = self._order()
        Order.objects.filter(pk=order.pk).update(status=Order.STATUS_SHIPPED, ttn="20450012345678")
        order.refresh_from_db()
        return order

    @patch("project.telegram_utils.send_telegram_message")
    def test_arrived_remind_received(self, send):
        order = self._shipped()
        now = timezone.now()
        row = {"Number": "20450012345678", "StatusCode": "7", "Status": "Прибув у відділення"}
        with patch("order.shipping._np_status", return_value=[row]):
            shipping.track_shipments(now)
            shipping.track_shipments(now + timedelta(hours=3))  # no repeat
            self.assertEqual(send.call_count, 1)
            self.assertIn("Посилка прибула", send.call_args.args[0])
            shipping.track_shipments(now + timedelta(days=3, hours=1))
            self.assertIn("не забирають", send.call_args.args[0])
            self.assertEqual(send.call_count, 2)
        row = dict(row, StatusCode="9", Status="Відправлення отримано")
        with patch("order.shipping._np_status", return_value=[row]):
            shipping.track_shipments(now + timedelta(days=4))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertIn("Виконано", send.call_args.args[0])

    @patch("project.telegram_utils.send_telegram_message")
    def test_refused(self, send):
        order = self._shipped()
        row = {"Number": "20450012345678", "StatusCode": "102", "Status": "Відмова одержувача"}
        with patch("order.shipping._np_status", return_value=[row]):
            shipping.track_shipments()
        self.assertIn("Відмова одержувача", send.call_args.args[0])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_SHIPPED)

    def test_scheduler_timing(self):
        from social.management.commands.content_scheduler import order_jobs

        with patch("order.shipping.track_shipments", return_value="tracking: 1 checked") as track, \
                patch("order.review_request.send_due", return_value=0) as due, \
                patch("order.review_request.ask_staff_due", return_value=0):
            order_jobs(datetime(2026, 11, 28, 10, 0, tzinfo=KYIV))
            order_jobs(datetime(2026, 11, 28, 10, 30, tzinfo=KYIV))
            order_jobs(datetime(2026, 11, 28, 23, 0, tzinfo=KYIV))
            self.assertEqual(track.call_count, 1)
            due.assert_not_called()
            order_jobs(datetime(2026, 11, 28, 11, 0, tzinfo=KYIV))
            due.assert_called_once()


class ResendActionTests(_Fixture, TestCase):
    @patch("project.telegram_utils.send_telegram_message", return_value=True)
    def test_resend_sends_card_with_buttons(self, send):
        from django.contrib.admin.sites import site
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        order = self._order()
        admin = site._registry[Order]
        request = RequestFactory().post("/")
        request.user = get_user_model().objects.create_superuser("a@a.com", "x")
        with patch.object(admin, "message_user") as msg:
            admin.resend_to_telegram(request, Order.objects.filter(pk=order.pk))
        self.assertIn("🛒 Нове замовлення", send.call_args.args[0])
        rows = send.call_args.kwargs["reply_markup"]["inline_keyboard"]
        self.assertEqual(rows[1][0]["callback_data"], f"ordst:{order.pk}")
        self.assertIn("1 з 1", msg.call_args.args[1])
