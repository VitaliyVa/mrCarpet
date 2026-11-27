"""
Order status push to Rozetka from our admin (project/rozetka_status.py).

The Rozetka client is a MagicMock; the background thread is replaced by an
inline call, and on_commit callbacks are run by captureOnCommitCallbacks.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from order.models import Order
from project import rozetka_status
from project.models import RozetkaSettings
from project.rozetka_api import RozetkaError
from project.rozetka_orders import cancel_order
from project.rozetka_status import (
    CANCEL_SKIP,
    RZ_CONFIRMED,
    RZ_IN_PROGRESS,
    RZ_SHIPPED,
    Push,
    join_note,
    push_for_change,
    push_status,
)


def inline(fn, *args):
    fn(*args)


def make_order(**kwargs):
    data = dict(
        source=Order.SOURCE_ROZETKA,
        rozetka_order_id=900001,
        order_number=900001,
        status=Order.STATUS_NEW,
        name="Олена",
        surname="Коваль",
        phone="+380501112233",
        payment_type=Order.PAYMENT_CASH,
        message="Rozetka №900001",
    )
    data.update(kwargs)
    return Order.objects.create(**data)


class MappingTests(TestCase):
    def test_paid_maps_to_confirmed(self):
        order = make_order(status=Order.STATUS_PAID)
        push = push_for_change(order, {"status": Order.STATUS_NEW, "ttn": ""})
        self.assertEqual(push.status, RZ_CONFIRMED)
        self.assertEqual(push.ttn, "")

    def test_shipped_with_ttn_maps_to_3(self):
        order = make_order(status=Order.STATUS_SHIPPED, ttn=" 20450000000001 ")
        push = push_for_change(order, {"status": Order.STATUS_PAID, "ttn": ""})
        self.assertEqual((push.status, push.ttn), (RZ_SHIPPED, "20450000000001"))

    def test_shipped_without_ttn_sends_nothing(self):
        order = make_order(status=Order.STATUS_SHIPPED)
        self.assertIsNone(push_for_change(order, {"status": Order.STATUS_PAID, "ttn": ""}))

    def test_new_ttn_on_shipped_order_is_sent(self):
        order = make_order(status=Order.STATUS_SHIPPED, ttn="222")
        push = push_for_change(order, {"status": Order.STATUS_SHIPPED, "ttn": "111"})
        self.assertEqual((push.status, push.ttn), (RZ_SHIPPED, "222"))
        self.assertIsNone(push_for_change(order, {"status": Order.STATUS_SHIPPED, "ttn": "222"}))

    def test_cancel_uses_chosen_reason(self):
        order = make_order(status=Order.STATUS_CANCELLED)
        push = push_for_change(order, {"status": Order.STATUS_NEW, "ttn": ""}, "42")
        self.assertEqual(push.status, 42)
        self.assertIn("Немає в наявності", push.comment)
        self.assertIsNone(push_for_change(order, {"status": Order.STATUS_NEW, "ttn": ""}, CANCEL_SKIP))
        self.assertIsNone(push_for_change(order, {"status": Order.STATUS_NEW, "ttn": ""}, "6"))

    def test_completed_and_same_status_send_nothing(self):
        order = make_order(status=Order.STATUS_COMPLETED)
        self.assertIsNone(push_for_change(order, {"status": Order.STATUS_SHIPPED, "ttn": "1"}))
        order.status = Order.STATUS_PAID
        self.assertIsNone(push_for_change(order, {"status": Order.STATUS_PAID, "ttn": ""}))

    def test_site_order_never_pushed(self):
        order = make_order(source=Order.SOURCE_SITE, rozetka_order_id=None, status=Order.STATUS_PAID)
        self.assertIsNone(push_for_change(order, {"status": Order.STATUS_NEW, "ttn": ""}))

    def test_join_note_keeps_import_notes(self):
        base = "Rozetka №1\nНедостатньо залишку: «Килим» замовлено 2, було 1"
        noisy = base + "".join(f"\nRozetka ✗ [2] x, {i}: " + "e" * 100 for i in range(12))
        result = join_note(noisy, "Rozetka ✓ [3 ТТН 1] y")
        self.assertLessEqual(len(result), 1024)
        self.assertTrue(result.startswith(base))
        self.assertTrue(result.endswith("Rozetka ✓ [3 ТТН 1] y"))


class PushTests(TestCase):
    def setUp(self):
        cfg = RozetkaSettings.load()
        cfg.enabled = True
        cfg.username = "seller"
        cfg.password = "pw"
        cfg.save()
        self.client_mock = MagicMock()
        patcher = patch.object(rozetka_status, "RozetkaClient", return_value=self.client_mock)
        patcher.start()
        self.addCleanup(patcher.stop)
        tg = patch("project.telegram_utils.send_telegram_message_async")
        self.telegram = tg.start()
        self.addCleanup(tg.stop)

    def test_success_is_recorded_and_not_repeated(self):
        order = make_order(status=Order.STATUS_PAID)
        push = Push(RZ_CONFIRMED, our_status=Order.STATUS_PAID)
        ok, _ = push_status(order.pk, push)
        self.assertTrue(ok)
        self.client_mock.change_status.assert_called_once_with(
            900001, RZ_CONFIRMED, ttn=None, seller_comment=None
        )
        order.refresh_from_db()
        self.assertIn("Rozetka ✓ [2]", order.message)
        self.assertTrue(order.message.startswith("Rozetka №900001"))
        push_status(order.pk, push)
        self.assertEqual(self.client_mock.change_status.call_count, 1)

    def test_shipped_sends_ttn_and_falls_back_to_2(self):
        order = make_order(status=Order.STATUS_SHIPPED, ttn="20450000000001")
        self.client_mock.change_status.side_effect = [RozetkaError("bad transition"), {}]
        ok, line = push_status(order.pk, Push(RZ_SHIPPED, ttn="20450000000001",
                                              our_status=Order.STATUS_SHIPPED))
        self.assertTrue(ok)
        first, second = self.client_mock.change_status.call_args_list
        self.assertEqual(first.args, (900001, RZ_SHIPPED))
        self.assertEqual(first.kwargs["ttn"], "20450000000001")
        self.assertEqual(second.args, (900001, RZ_CONFIRMED))
        self.assertEqual(second.kwargs["ttn"], "20450000000001")
        self.assertIn("Rozetka ✓ [3 ТТН 20450000000001]", line)

    def test_error_is_recorded_and_never_raises(self):
        order = make_order(status=Order.STATUS_PAID)
        self.client_mock.change_status.side_effect = RozetkaError("[1010] access_denied")
        self.client_mock.get_order.return_value = {
            "status_available": [{"parent_id": 1, "child_id": 26}, {"parent_id": 1, "child_id": 42}]
        }
        ok, error = push_status(order.pk, Push(RZ_CONFIRMED, our_status=Order.STATUS_PAID))
        self.assertFalse(ok)
        order.refresh_from_db()
        self.assertIn("Rozetka ✗ [2]", order.message)
        self.assertIn("access_denied", order.message)
        self.assertIn("26, 42", order.message)

    def test_stale_push_skipped(self):
        order = make_order(status=Order.STATUS_CANCELLED)
        ok, _ = push_status(order.pk, Push(RZ_CONFIRMED, our_status=Order.STATUS_PAID))
        self.assertFalse(ok)
        self.client_mock.change_status.assert_not_called()

    def test_site_order_not_sent(self):
        order = make_order(source=Order.SOURCE_SITE, rozetka_order_id=None, status=Order.STATUS_PAID)
        push_status(order.pk, Push(RZ_CONFIRMED))
        self.client_mock.change_status.assert_not_called()

    def test_rozetka_side_cancellation_does_not_echo(self):
        order = make_order()
        with patch.object(rozetka_status, "start_background", side_effect=inline):
            with self.captureOnCommitCallbacks(execute=True):
                cancel_order(900001)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.client_mock.change_status.assert_not_called()


class AdminTests(TestCase):
    def setUp(self):
        cfg = RozetkaSettings.load()
        cfg.enabled = True
        cfg.username = "seller"
        cfg.password = "pw"
        cfg.save()
        self.client_mock = MagicMock()
        for target, kwargs in (
            (patch.object(rozetka_status, "RozetkaClient", return_value=self.client_mock), {}),
            (patch.object(rozetka_status, "start_background", side_effect=inline), {}),
            (patch("project.telegram_utils.send_telegram_message_async"), {}),
        ):
            target.start()
            self.addCleanup(target.stop)
        user = get_user_model().objects.create_superuser(email="m@example.com", password="x")
        self.client.force_login(user)

    def _post(self, order, **changes):
        data = {
            "status": order.status,
            "payment_type": order.payment_type,
            "name": order.name,
            "surname": order.surname,
            "email": order.email or "",
            "phone": order.phone or "",
            "city": order.city or "",
            "address": order.address or "",
            "ttn": order.ttn or "",
            "message": order.message or "",
            "total_price": "",
            "promocode": "",
            "free_shipping_threshold": "",
            "rozetka_cancel_reason": "",
        }
        data.update(changes)
        url = reverse("admin:order_order_change", args=[order.pk])
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data)

    def test_admin_paid_pushes_once(self):
        order = make_order()
        response = self._post(order, status=Order.STATUS_PAID)
        self.assertEqual(response.status_code, 302)
        self.client_mock.change_status.assert_called_once_with(
            900001, RZ_CONFIRMED, ttn=None, seller_comment=None
        )
        order.refresh_from_db()
        self._post(order)  # saved again, same status: no second call
        self.assertEqual(self.client_mock.change_status.call_count, 1)

    def test_admin_shipped_requires_ttn(self):
        order = make_order(status=Order.STATUS_PAID)
        response = self._post(order, status=Order.STATUS_SHIPPED)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "без ТТН")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PAID)
        self.client_mock.change_status.assert_not_called()

        response = self._post(order, status=Order.STATUS_SHIPPED, ttn="20450000000001")
        self.assertEqual(response.status_code, 302)
        self.client_mock.change_status.assert_called_once()
        self.assertEqual(self.client_mock.change_status.call_args.args, (900001, RZ_SHIPPED))
        self.assertEqual(self.client_mock.change_status.call_args.kwargs["ttn"], "20450000000001")

    def test_admin_cancel_requires_reason(self):
        order = make_order()
        response = self._post(order, status=Order.STATUS_CANCELLED)
        self.assertEqual(response.status_code, 200)
        self.client_mock.change_status.assert_not_called()
        response = self._post(order, status=Order.STATUS_CANCELLED, rozetka_cancel_reason="18")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client_mock.change_status.call_args.args, (900001, 18))

    def test_admin_cancel_skip_sends_nothing(self):
        order = make_order()
        response = self._post(order, status=Order.STATUS_CANCELLED, rozetka_cancel_reason=CANCEL_SKIP)
        self.assertEqual(response.status_code, 302)
        self.client_mock.change_status.assert_not_called()

    def test_admin_error_does_not_break_save(self):
        self.client_mock.change_status.side_effect = RozetkaError("boom")
        self.client_mock.get_order.side_effect = RozetkaError("boom too")
        order = make_order()
        response = self._post(order, status=Order.STATUS_PAID)
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PAID)
        self.assertIn("Rozetka ✗ [2]", order.message)

    def test_admin_schedule_crash_does_not_break_save(self):
        order = make_order()
        with patch.object(rozetka_status, "schedule", side_effect=RuntimeError("x")):
            response = self._post(order, status=Order.STATUS_PAID)
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PAID)

    def test_site_order_admin_save_never_calls_rozetka(self):
        order = make_order(source=Order.SOURCE_SITE, rozetka_order_id=None, order_number=5)
        response = self._post(order, status=Order.STATUS_SHIPPED)
        self.assertEqual(response.status_code, 302)
        response = self._post(order, status=Order.STATUS_CANCELLED)
        self.assertEqual(response.status_code, 302)
        self.client_mock.change_status.assert_not_called()

    def test_confirm_action(self):
        new = make_order()
        paid = make_order(rozetka_order_id=900002, order_number=900002, status=Order.STATUS_PAID)
        site = make_order(source=Order.SOURCE_SITE, rozetka_order_id=None, order_number=7)
        url = reverse("admin:order_order_changelist")
        payload = {
            "action": "confirm_on_rozetka",
            "_selected_action": [new.pk, paid.pk, site.pk],
        }
        for _ in range(2):  # second click is deduped by the ✓ note
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, payload)
            self.assertEqual(response.status_code, 302)
        self.client_mock.change_status.assert_called_once_with(
            900001, RZ_IN_PROGRESS, ttn=None, seller_comment=None
        )
        new.refresh_from_db()
        self.assertIn("Rozetka ✓ [26]", new.message)
        self.assertEqual(new.status, Order.STATUS_NEW)

    def test_change_page_shows_rozetka_block_only_for_rozetka(self):
        order = make_order()
        site = make_order(source=Order.SOURCE_SITE, rozetka_order_id=None, order_number=8)
        page = self.client.get(reverse("admin:order_order_change", args=[order.pk]))
        self.assertContains(page, "Причина скасування для Rozetka")
        self.assertContains(page, 'name="ttn"')
        page = self.client.get(reverse("admin:order_order_change", args=[site.pk]))
        self.assertNotContains(page, "Причина скасування для Rozetka")
        self.assertContains(page, 'name="ttn"')
