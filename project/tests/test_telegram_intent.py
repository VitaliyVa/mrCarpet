from django.test import TestCase

from order.models import Order
from project.telegram_agent.intent import (
    extract_order_number,
    maybe_direct_plan,
)
from project.telegram_agent.status_labels import (
    normalize_status,
    status_list_reply,
)
from project.telegram_agent.tools import (
    BATCH_TOOL,
    describe_write,
    execute_write_calls,
    format_write_result_ua,
    validate_write_calls,
)


class StatusLabelsTests(TestCase):
    def test_normalize_ua_and_en(self):
        self.assertEqual(normalize_status("Виконано"), "completed")
        self.assertEqual(normalize_status("completed"), "completed")
        self.assertEqual(normalize_status("нове"), "new")

    def test_status_list_is_ukrainian(self):
        text = status_list_reply()
        self.assertIn("Виконано", text)
        self.assertIn("Нове", text)
        self.assertIn("completed", text)
        self.assertNotIn("awaiting_payment, paid", text)


class IntentRouterTests(TestCase):
    def test_analytics_dashboard(self):
        plan = maybe_direct_plan("містер карпет, покажи аналітику")
        self.assertEqual(plan["type"], "tool")
        self.assertEqual(plan["name"], "get_ga4_report")
        self.assertEqual(plan["args"]["report"], "dashboard")
        self.assertEqual(plan["args"]["days"], 7)

    def test_analytics_funnel_days(self):
        plan = maybe_direct_plan("воронка за 14 днів")
        self.assertEqual(plan["type"], "tool")
        self.assertEqual(plan["name"], "get_ga4_report")
        self.assertEqual(plan["args"]["report"], "ecommerce")
        self.assertEqual(plan["args"]["days"], 14)

    def test_analytics_realtime(self):
        plan = maybe_direct_plan("покажи realtime ga4")
        self.assertEqual(plan["type"], "tool")
        self.assertEqual(plan["name"], "get_ga4_report")
        self.assertEqual(plan["args"]["report"], "realtime")

    def test_general_analytics_still_means_the_whole_dashboard(self):
        """
        The social slide rides along with the full album rather than
        replacing it — asking broadly must not narrow the answer.
        """
        for text in ("скинь аналітику", "покажи аналітику за тиждень", "dashboard"):
            plan = maybe_direct_plan(text)
            self.assertEqual(plan["args"]["report"], "dashboard", text)

    def test_asking_about_the_networks_returns_only_that_slide(self):
        for text in (
            "скинь аналітику по соцмережах",
            "статистика соцмереж",
            "покажи метрики інстаграму",
            "аналітика по tiktok",
        ):
            plan = maybe_direct_plan(text)
            self.assertEqual(plan["name"], "get_ga4_report", text)
            self.assertEqual(plan["args"]["report"], "social", text)

    def test_social_days_are_parsed_like_the_others(self):
        plan = maybe_direct_plan("статистика соцмереж за 14 днів")
        self.assertEqual(plan["args"]["report"], "social")
        self.assertEqual(plan["args"]["days"], 14)

    def test_ordinary_talk_about_posting_is_not_a_report_request(self):
        """
        A bare "соцмережі" turns up in normal conversation. Answering it with
        a chart would make the bot tiresome, so an analytics word is required.
        """
        for text in (
            "треба більше постити в соцмережах",
            "давай запустимо рекламу в інстаграмі",
        ):
            plan = maybe_direct_plan(text)
            if plan and plan.get("name") == "get_ga4_report":
                self.fail(f"{text!r} should not trigger a report")

    def test_list_statuses(self):
        plan = maybe_direct_plan("які є статуси?")
        self.assertEqual(plan["type"], "reply")
        self.assertIn("Виконано", plan["text"])

    def test_current_status_question_is_get_order(self):
        plan = maybe_direct_plan("який статус в замовлені №9106492351856?")
        self.assertEqual(plan["type"], "tool")
        self.assertEqual(plan["name"], "get_order")
        self.assertEqual(plan["args"]["order_number"], 9106492351856)

    def test_current_status_from_reply_context(self):
        plan = maybe_direct_plan(
            "який статус в замовлені?",
            context_text="✅ Замовлення оплачено №9106492351856 Статус: Оплачено",
        )
        self.assertEqual(plan["type"], "tool")
        self.assertEqual(plan["name"], "get_order")
        self.assertEqual(plan["args"]["order_number"], 9106492351856)

    def test_status_change_with_email_batch(self):
        Order.objects.create(
            order_number=9384126709151,
            name="Іван",
            surname="Тест",
            phone="+380000000000",
            email="client@example.com",
            status=Order.STATUS_NEW,
            payment_type=Order.PAYMENT_CASH,
            total_price=1000,
        )
        plan = maybe_direct_plan(
            "зміни на статус completed і напиши клієнту листа",
            context_text="🛒 Нове замовлення №9384126709151 Статус: Нове",
        )
        self.assertEqual(plan["type"], "tools")
        names = [c["name"] for c in plan["calls"]]
        self.assertEqual(names, ["set_order_status", "send_order_email"])
        self.assertEqual(plan["calls"][0]["args"]["status"], "completed")
        self.assertEqual(plan["calls"][1]["args"]["order_number"], 9384126709151)
        self.assertIn("Виконано", plan["calls"][1]["args"]["subject"])

    def test_status_change_does_not_become_stock(self):
        plan = maybe_direct_plan(
            "зміни на статус completed і напиши клієнту листа",
            context_text="Килим прямокутний бежевий 0010B розмір 0.8х1.5 2 шт",
        )
        # no order number → no stock either
        self.assertIsNone(plan)

    def test_status_from_history_context(self):
        Order.objects.create(
            order_number=1112223334445,
            name="Оля",
            surname="К",
            phone="+380111111111",
            email="olya@example.com",
            status=Order.STATUS_PAID,
            payment_type=Order.PAYMENT_CASH,
            total_price=500,
        )
        plan = maybe_direct_plan(
            "містер карпет в замовленні зміни на статус виконано і напиши клієнту лист",
            context_text="раніше: замовлення №1112223334445 оплачено",
        )
        self.assertIsNotNone(plan)
        if plan["type"] == "write":
            self.assertEqual(plan["name"], "set_order_status")
        else:
            self.assertIn("set_order_status", [c["name"] for c in plan["calls"]])
            self.assertIn("send_order_email", [c["name"] for c in plan["calls"]])

    def test_extract_order_number(self):
        self.assertEqual(
            extract_order_number("🛒 Нове замовлення №9384126709151 Статус: Нове"),
            9384126709151,
        )


class BatchValidateTests(TestCase):
    def test_validate_status_and_email(self):
        Order.objects.create(
            order_number=5556667778889,
            name="Боб",
            surname="Б",
            phone="+380222222222",
            email="bob@example.com",
            status=Order.STATUS_NEW,
            payment_type=Order.PAYMENT_CASH,
            total_price=200,
        )
        ok, err, steps = validate_write_calls(
            [
                {
                    "name": "set_order_status",
                    "args": {"order_number": 5556667778889, "status": "Виконано"},
                },
                {
                    "name": "send_order_email",
                    "args": {
                        "order_number": 5556667778889,
                        "subject": "Тема",
                        "body": "Текст листа",
                    },
                },
            ]
        )
        self.assertTrue(ok, err)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["args"]["status"], "completed")
        desc = describe_write(BATCH_TOOL, {"steps": steps})
        self.assertIn("Пакетна дія", desc)
        self.assertIn("Виконано", desc)
        self.assertIn("Надіслати лист", desc)

    def test_batch_partial_fail_ok_false(self):
        Order.objects.create(
            order_number=5556667778890,
            name="Боб",
            surname="Б",
            phone="+380222222222",
            email="bob@example.com",
            status=Order.STATUS_NEW,
            payment_type=Order.PAYMENT_CASH,
            total_price=200,
        )
        from unittest.mock import patch

        with patch(
            "project.smtp_utils.send_smtp_mail",
            return_value=False,
        ):
            result = execute_write_calls(
                [
                    {
                        "name": "set_order_status",
                        "args": {
                            "order_number": 5556667778890,
                            "status": "completed",
                        },
                    },
                    {
                        "name": "send_order_email",
                        "args": {
                            "order_number": 5556667778890,
                            "subject": "Тема",
                            "body": "Текст",
                            "email": "bob@example.com",
                        },
                    },
                ]
            )
        self.assertFalse(result["ok"])
        self.assertTrue(result["steps"][0]["ok"])
        self.assertFalse(result["steps"][1]["ok"])
        summary = format_write_result_ua(BATCH_TOOL, result)
        self.assertIn("частково", summary.casefold())


class FindOrdersIntentTests(TestCase):
    def test_find_by_phone(self):
        plan = maybe_direct_plan("знайди замовлення по телефону 0501234567")
        self.assertEqual(plan["type"], "tool")
        self.assertEqual(plan["name"], "find_orders")
        self.assertIn("0501234567", plan["args"]["phone"])

    def test_awaiting_payment_list(self):
        plan = maybe_direct_plan("покажи замовлення що очікують оплати")
        self.assertEqual(plan["name"], "list_recent_orders")
        self.assertEqual(plan["args"]["status"], "awaiting_payment")

    def test_get_order_from_context(self):
        plan = maybe_direct_plan(
            "покажи деталі замовлення",
            context_text="Нотифікація: замовлення №9384126709151 статус=Нове",
        )
        self.assertEqual(plan["name"], "get_order")
        self.assertEqual(plan["args"]["order_number"], 9384126709151)


class WebhookSecretTests(TestCase):
    def test_ai_ready_without_secret_is_403(self):
        from project.models import TelegramSettings

        settings = TelegramSettings.load()
        settings.is_enabled = True
        settings.ai_enabled = True
        settings.bot_token = "123:ABC"
        settings.chat_id = "-1001"
        settings.webhook_secret = ""
        settings.save()

        from django.test import Client

        client = Client()
        response = client.post(
            "/api/telegram/webhook/",
            data=b'{"update_id":1}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
