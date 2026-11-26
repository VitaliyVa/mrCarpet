"""
Rozetka buyer messages -> Telegram (project/rozetka_messages.py).

No network: a fake client yields chats / comments / calls, Telegram sending is
patched, RozetkaNotice rows are real (DB).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from project import rozetka_messages as rm
from project.models import RozetkaNotice, TelegramSettings
from project.rozetka_api import RozetkaError


def _now(delta_hours=0):
    return (rm.rozetka_now() + timedelta(hours=delta_hours)).strftime("%Y-%m-%d %H:%M:%S")


class FakeClient:
    def __init__(self, items=None, orders=None, comments=None, calls=None, fail=()):
        self.chats = {"items": items or [], "orders": orders or []}
        self.comments = comments or []
        self.calls = calls or []
        self.fail = set(fail)
        self.requests = []

    def _maybe_fail(self, name):
        self.requests.append(name)
        if name in self.fail:
            raise RozetkaError(f"{name} down")

    def iter_chats(self, *, msg_type="items", updated_from=None, **kwargs):
        self._maybe_fail(f"chats-{msg_type}")
        yield from self.chats[msg_type]

    def get_chat(self, chat_id, expand="messages,item"):
        self.requests.append(f"get_chat:{chat_id}")
        return {"id": chat_id, "messages": []}

    def iter_item_comments(self, *, created_from=None, expand="children", **kwargs):
        self._maybe_fail("comments")
        yield from self.comments

    def iter_calls(self, *, created_from=None, **kwargs):
        self._maybe_fail("calls")
        yield from self.calls


def buyer_msg(body, msg_id=None, hours=-1):
    msg = {"body": body, "created": _now(hours), "sender": 3, "seller": None,
           "seller_id": None, "receiver_id": 42}
    if msg_id is not None:
        msg["id"] = msg_id
    return msg


def seller_msg(body, msg_id=None, hours=-1):
    msg = {"body": body, "created": _now(hours), "sender": 2,
           "seller": {"id": 39, "login": "shop"}, "seller_id": 39}
    if msg_id is not None:
        msg["id"] = msg_id
    return msg


def item_chat(chat_id=101, messages=None, chat_type=1):
    return {
        "id": chat_id,
        "type": chat_type,
        "subject": "Питання",
        "user_fio": "Олена",
        "item": {"name_ua": "Килим Avalon 160x230", "name": "Ковер",
                 "url": "https://rozetka.com.ua/123/p123/"},
        "messages": messages if messages is not None else [buyer_msg("Є в наявності?", 1)],
    }


class NotifyBase(TestCase):
    def setUp(self):
        TelegramSettings.objects.update_or_create(
            pk=1, defaults={"is_enabled": True, "bot_token": "t", "chat_id": "1"}
        )
        patcher = patch("project.rozetka_messages._send", return_value=True)
        self.send = patcher.start()
        self.addCleanup(patcher.stop)

    def texts(self):
        return [call.args[0] for call in self.send.call_args_list]


class NotifyTests(NotifyBase):
    def test_product_question_sent_once_across_passes(self):
        client = FakeClient(items=[item_chat()])
        first = rm.notify_new_messages(client)
        second = rm.notify_new_messages(client)

        self.assertEqual(first, {"sent": 1, "errors": []})
        self.assertEqual(second, {"sent": 0, "errors": []})
        self.assertEqual(self.send.call_count, 1)
        text = self.texts()[0]
        self.assertTrue(text.startswith("<b>ROZETKA 💬 Питання про товар</b>"))
        self.assertIn('<a href="https://rozetka.com.ua/123/p123/">Килим Avalon 160x230</a>', text)
        self.assertIn("Покупець: Олена", text)
        self.assertIn("Є в наявності?", text)
        self.assertIn(rm.SELLER_CABINET_URL, text)
        self.assertTrue(RozetkaNotice.objects.filter(key="chat:101:1", kind="chat").exists())

    def test_seller_and_system_messages_skipped(self):
        system = {"body": "Нове замовлення", "created": _now(-1), "sender": 0,
                  "seller": None, "seller_id": None, "id": 5}
        chat = item_chat(messages=[seller_msg("Так, є", 2), system])
        result = rm.notify_new_messages(FakeClient(items=[chat]))
        self.assertEqual(result["sent"], 0)
        self.send.assert_not_called()
        self.assertFalse(RozetkaNotice.objects.exists())

    def test_new_message_in_known_chat_sends_only_new_text(self):
        chat = item_chat(messages=[buyer_msg("Перше питання", 1)])
        client = FakeClient(items=[chat])
        rm.notify_new_messages(client)
        chat["messages"] += [seller_msg("Відповідь", 2), buyer_msg("Друге питання", 3)]
        rm.notify_new_messages(client)

        self.assertEqual(self.send.call_count, 2)
        second = self.texts()[1]
        self.assertIn("Друге питання", second)
        self.assertNotIn("Перше питання", second)
        self.assertNotIn("Відповідь", second)

    def test_several_messages_of_one_chat_combined(self):
        chat = item_chat(messages=[buyer_msg("Раз", 1, -3), buyer_msg("Два", 2, -2)])
        result = rm.notify_new_messages(FakeClient(items=[chat]))
        self.assertEqual(result["sent"], 1)
        text = self.texts()[0]
        self.assertLess(text.index("Раз"), text.index("Два"))
        self.assertEqual(RozetkaNotice.objects.count(), 2)

    def test_missing_message_id_uses_created_and_body_hash(self):
        msg = buyer_msg("Без id")
        client = FakeClient(items=[item_chat(chat_id=7, messages=[msg])])
        rm.notify_new_messages(client)
        rm.notify_new_messages(client)

        self.assertEqual(self.send.call_count, 1)
        key = RozetkaNotice.objects.get().key
        self.assertEqual(key, f"chat:7:{rm.message_key(msg)}")
        self.assertTrue(key.startswith("chat:7:" + msg["created"].replace(" ", "T") + "-"))
        other = dict(msg, body="Інший текст")
        self.assertNotEqual(rm.message_key(msg), rm.message_key(other))

    def test_old_messages_outside_lookback_skipped(self):
        chat = item_chat(messages=[buyer_msg("Давнє", 1, hours=-24 * 5)])
        rm.notify_new_messages(FakeClient(items=[chat]))
        self.send.assert_not_called()

    def test_html_escaped(self):
        chat = item_chat(messages=[buyer_msg("<b>ціна</b> & знижка?", 1)])
        chat["user_fio"] = "Іван <script>"
        chat["item"]["name_ua"] = "Килим <Lux>"
        rm.notify_new_messages(FakeClient(items=[chat]))
        text = self.texts()[0]
        self.assertIn("&lt;b&gt;ціна&lt;/b&gt; &amp; знижка?", text)
        self.assertIn("Іван &lt;script&gt;", text)
        self.assertIn("Килим &lt;Lux&gt;", text)
        self.assertNotIn("<script>", text)

    def test_long_text_trimmed(self):
        chat = item_chat(messages=[buyer_msg("а" * 5000, 1)])
        rm.notify_new_messages(FakeClient(items=[chat]))
        text = self.texts()[0]
        self.assertIn("а" * 1000, text)
        self.assertNotIn("а" * (rm.TEXT_LIMIT + 1), text)
        self.assertLess(len(text), 4096)

    def test_order_chat_kind_and_seller_question(self):
        order_chat = {"id": 300, "type": 0, "order_id": 555777, "user": {"contact_fio": "Петро"},
                      "messages": [buyer_msg("Коли відправите?", 9)]}
        seller_chat = item_chat(chat_id=301, chat_type=2, messages=[buyer_msg("Є доставка?", 10)])
        seller_chat["item"] = None
        result = rm.notify_new_messages(FakeClient(items=[seller_chat], orders=[order_chat]))
        self.assertEqual(result["sent"], 2)
        joined = "\n".join(self.texts())
        self.assertIn("ROZETKA 💬 Повідомлення по замовленню №555777", joined)
        self.assertIn("Покупець: Петро", joined)
        self.assertIn("ROZETKA 💬 Питання продавцю", joined)

    def test_comments_reviews_and_replies(self):
        comments = [
            {"id": 11, "type": "comment", "mark": 5, "name": "Марія", "text": "Гарний килим",
             "created": _now(-2), "seller_id": 0,
             "record": {"id": "1", "title": "Килим Record"},
             "item": {"name_ua": None, "name": None, "url": "https://rozetka.com.ua/1/p1/"},
             "children": [
                 {"id": 12, "name": "Магазин", "text": "Дякуємо", "created": _now(-1),
                  "is_market": 1, "seller_id": None},
                 {"id": 13, "name": "Марія", "text": "А ще є?", "created": _now(-1),
                  "is_market": 0, "seller_id": None},
             ]},
            {"id": 14, "type": "question", "mark": 0, "name": "Ігор", "text": "Який ворс?",
             "created": _now(-1), "seller_id": 0, "item": {"name_ua": "Килим Q",
                                                         "url": "https://rozetka.com.ua/2/p2/"},
             "children": []},
        ]
        client = FakeClient(comments=comments)
        result = rm.notify_new_messages(client)
        self.assertEqual(result["sent"], 3)
        joined = "\n".join(self.texts())
        self.assertIn("Відгук ★5", joined)
        self.assertIn("Килим Record", joined)
        self.assertIn("Запитання під товаром", joined)
        self.assertIn("А ще є?", joined)
        self.assertNotIn("Дякуємо", joined)
        self.assertEqual(
            set(RozetkaNotice.objects.values_list("key", flat=True)),
            {"comment:11", "comment:13", "comment:14"},
        )
        self.assertEqual(rm.notify_new_messages(client)["sent"], 0)

    def test_calls(self):
        calls = [{"id": 264, "request_type_name": "Прохання зв'язатися", "message": "Зателефонуйте",
                  "user_login": "valentyn", "user_phone": "380733071775", "order_id": 177318319,
                  "code_id": None, "date_call": _now(-1)}]
        result = rm.notify_new_messages(FakeClient(calls=calls))
        self.assertEqual(result["sent"], 1)
        text = self.texts()[0]
        self.assertIn("ROZETKA 💬 Звернення", text)
        self.assertIn("Замовлення №177318319", text)
        self.assertIn("380733071775", text)
        self.assertTrue(RozetkaNotice.objects.filter(key="call:264", kind="call").exists())

    def test_one_endpoint_error_does_not_block_others(self):
        calls = [{"id": 1, "message": "Звернення", "date_call": _now(-1)}]
        client = FakeClient(items=[item_chat()], calls=calls, fail={"chats-orders", "comments"})
        result = rm.notify_new_messages(client)
        self.assertEqual(result["sent"], 2)
        self.assertEqual(len(result["errors"]), 2)
        self.assertTrue(result["errors"][0].startswith("chats-orders:"))
        self.assertTrue(result["errors"][1].startswith("comments:"))

    def test_cap_per_pass(self):
        chats = [item_chat(chat_id=i, messages=[buyer_msg(f"q{i}", i)]) for i in range(1, 26)]
        client = FakeClient(items=chats)
        first = rm.notify_new_messages(client)
        self.assertEqual(first["sent"], rm.MAX_TELEGRAM_PER_PASS)
        second = rm.notify_new_messages(client)
        self.assertEqual(second["sent"], 25 - rm.MAX_TELEGRAM_PER_PASS)
        self.assertEqual(rm.notify_new_messages(client)["sent"], 0)
        self.assertEqual(RozetkaNotice.objects.count(), 25)

    def test_failed_send_not_marked_and_retried(self):
        client = FakeClient(items=[item_chat()])
        self.send.side_effect = RuntimeError("telegram down")
        result = rm.notify_new_messages(client)
        self.assertEqual(result["sent"], 0)
        self.assertTrue(result["errors"][0].startswith("telegram:"))
        self.assertFalse(RozetkaNotice.objects.exists())

        self.send.side_effect = None
        self.send.return_value = False
        self.assertEqual(rm.notify_new_messages(client)["sent"], 0)
        self.assertFalse(RozetkaNotice.objects.exists())

        self.send.return_value = True
        self.assertEqual(rm.notify_new_messages(client)["sent"], 1)
        self.assertEqual(RozetkaNotice.objects.count(), 1)

    def test_existing_notice_race_is_harmless(self):
        RozetkaNotice.objects.create(key="chat:101:1", kind="chat")
        result = rm.notify_new_messages(FakeClient(items=[item_chat()]))
        self.assertEqual(result, {"sent": 0, "errors": []})
        rm._mark(["chat:101:1"], "chat")  # get_or_create on an existing key
        self.assertEqual(RozetkaNotice.objects.count(), 1)

    def test_never_raises(self):
        with patch("project.rozetka_messages._notify", side_effect=ValueError("boom")):
            result = rm.notify_new_messages(FakeClient())
        self.assertEqual(result, {"sent": 0, "errors": ["boom"]})

    def test_chat_without_messages_field_opens_chat(self):
        chat = item_chat()
        del chat["messages"]
        client = FakeClient(items=[chat])
        rm.notify_new_messages(client)
        self.assertIn("get_chat:101", client.requests)


class TelegramOffTests(NotifyBase):
    def test_nothing_marked_when_telegram_not_configured(self):
        TelegramSettings.objects.filter(pk=1).update(is_enabled=False)
        client = FakeClient(items=[item_chat()])
        result = rm.notify_new_messages(client)
        self.assertEqual(result, {"sent": 0, "errors": []})
        self.assertEqual(client.requests, [])
        self.assertFalse(RozetkaNotice.objects.exists())


class BuyerDetectionTests(TestCase):
    def test_is_buyer_message(self):
        self.assertTrue(rm.is_buyer_message({"sender": 3, "seller_id": None}))
        self.assertTrue(rm.is_buyer_message({"sender": "3", "seller_id": "0"}))
        self.assertFalse(rm.is_buyer_message({"sender": 2, "seller_id": None}))
        self.assertFalse(rm.is_buyer_message({"sender": 3, "seller_id": 39}))
        self.assertFalse(rm.is_buyer_message({"sender": 1, "seller": {"id": 1}}))
        self.assertFalse(rm.is_buyer_message({"sender": 0}))
        self.assertTrue(rm.is_buyer_message({"body": "x"}))
