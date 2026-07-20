"""Tests: HITL-відповіді на коменти через сімейний чат."""

from unittest.mock import patch

from django.test import TestCase

from social.models import SocialCommentReply
from social.services.comment_reply import (
    handle_reply_callback,
    maybe_handle_staff_reply,
)

FAMILY_CHAT = "-1002034341046"


def _record(**kwargs):
    defaults = dict(
        platform="facebook",
        external_comment_id="111_222",
        comment_text="Чи є такі розміри?",
        author_name="Клієнт",
        alert_chat_id=FAMILY_CHAT,
        alert_message_id="500",
    )
    defaults.update(kwargs)
    return SocialCommentReply.objects.create(**defaults)


def _reply_msg(reply_to="500", text="нє, нема", chat=FAMILY_CHAT):
    return {
        "message_id": 600,
        "chat": {"id": int(chat)},
        "from": {"id": 42, "first_name": "Vitaliy"},
        "message_thread_id": 971,
        "reply_to_message": {"message_id": int(reply_to)},
        "text": text,
    }


class StaffReplyMatcherTests(TestCase):
    @patch("social.services.comment_reply.send_message", return_value={"ok": True, "result": {"message_id": 601}})
    @patch("social.services.comment_reply.generate_reply", return_value="Доброго дня! На жаль, таких розмірів немає.")
    def test_reply_on_alert_creates_draft(self, mock_llm, mock_send):
        record = _record()
        handled = maybe_handle_staff_reply(_reply_msg())
        self.assertTrue(handled)
        record.refresh_from_db()
        self.assertEqual(record.status, SocialCommentReply.Status.AWAITING)
        self.assertEqual(record.raw_operator_text, "нє, нема")
        self.assertIn("немає", record.draft_text)
        self.assertEqual(record.draft_message_id, "601")
        # кнопки в чернетці
        kwargs = mock_send.call_args[1]
        buttons = kwargs["reply_markup"]["inline_keyboard"][0]
        self.assertEqual(len(buttons), 3)
        # LLM отримав контекст комента і оператора
        llm_kwargs = mock_llm.call_args[1]
        self.assertEqual(llm_kwargs["comment_text"], "Чи є такі розміри?")
        self.assertEqual(llm_kwargs["operator_text"], "нє, нема")

    @patch("social.services.comment_reply.send_message", return_value={"ok": True, "result": {"message_id": 602}})
    @patch("social.services.comment_reply.generate_reply", return_value="Оновлений варіант відповіді.")
    def test_reply_on_draft_regenerates_with_instruction(self, mock_llm, _send):
        record = _record(
            status=SocialCommentReply.Status.AWAITING,
            raw_operator_text="нема",
            draft_text="Старий драфт",
            draft_message_id="601",
        )
        handled = maybe_handle_staff_reply(
            _reply_msg(reply_to="601", text="додай що завтра буде поставка")
        )
        self.assertTrue(handled)
        record.refresh_from_db()
        self.assertEqual(record.draft_text, "Оновлений варіант відповіді.")
        self.assertIn(
            "завтра буде поставка",
            mock_llm.call_args[1]["extra_instruction"],
        )

    @patch("social.services.comment_reply.send_message", return_value={"ok": True, "result": {"message_id": 601}})
    @patch("social.services.comment_reply.generate_reply", return_value="Відповідь")
    def test_telegram_retry_deduped(self, mock_llm, _send):
        _record()
        msg = _reply_msg()
        self.assertTrue(maybe_handle_staff_reply(msg))
        # той самий update повторно (ретрай Telegram) — LLM не смикається
        self.assertTrue(maybe_handle_staff_reply(msg))
        mock_llm.assert_called_once()

    def test_unrelated_reply_ignored(self):
        _record()
        handled = maybe_handle_staff_reply(_reply_msg(reply_to="999"))
        self.assertFalse(handled)

    def test_non_reply_ignored(self):
        _record()
        msg = _reply_msg()
        del msg["reply_to_message"]
        self.assertFalse(maybe_handle_staff_reply(msg))

    def test_wrong_chat_ignored(self):
        _record()
        self.assertFalse(maybe_handle_staff_reply(_reply_msg(chat="-100999")))


class CallbackTests(TestCase):
    def _callback(self, action, rid, chat=FAMILY_CHAT):
        return {
            "id": "cq1",
            "data": f"{action}:{rid}",
            "message": {"message_id": 601, "chat": {"id": int(chat)}},
        }

    @patch("social.services.comment_reply.edit_message_text")
    @patch("social.services.comment_reply.answer_callback_query")
    @patch("social.services.comment_reply._fb_reply", return_value={"ok": True, "external_id": "999"})
    def test_confirm_sends_to_platform(self, mock_fb, _cq, _edit):
        record = _record(
            status=SocialCommentReply.Status.AWAITING,
            draft_text="Доброго дня! На жаль, немає.",
        )
        handled = handle_reply_callback(self._callback("crok", record.pk))
        self.assertTrue(handled)
        record.refresh_from_db()
        self.assertEqual(record.status, SocialCommentReply.Status.SENT)
        self.assertEqual(record.sent_external_id, "999")
        mock_fb.assert_called_once_with("111_222", "Доброго дня! На жаль, немає.")

    @patch("social.services.comment_reply.edit_message_text")
    @patch("social.services.comment_reply.answer_callback_query")
    @patch("social.services.comment_reply._fb_reply", return_value={"ok": True, "external_id": "999"})
    def test_double_confirm_sends_once(self, mock_fb, mock_cq, _edit):
        record = _record(
            status=SocialCommentReply.Status.AWAITING, draft_text="Текст"
        )
        handle_reply_callback(self._callback("crok", record.pk))
        # другий клік по вже відправленому — платформа НЕ викликається вдруге
        handle_reply_callback(self._callback("crok", record.pk))
        mock_fb.assert_called_once()

    @patch("social.services.comment_reply.edit_message_text")
    @patch("social.services.comment_reply.answer_callback_query")
    @patch("social.services.comment_reply._fb_reply", return_value={"ok": False, "error": "boom"})
    def test_failed_send_allows_retry(self, mock_fb, _cq, _edit):
        record = _record(
            status=SocialCommentReply.Status.AWAITING, draft_text="Текст"
        )
        handle_reply_callback(self._callback("crok", record.pk))
        record.refresh_from_db()
        self.assertEqual(record.status, SocialCommentReply.Status.FAILED)
        # ретрай після фейла дозволений (claim приймає FAILED)
        handle_reply_callback(self._callback("crok", record.pk))
        self.assertEqual(mock_fb.call_count, 2)

    @patch("social.services.comment_reply.edit_message_text")
    @patch("social.services.comment_reply.answer_callback_query")
    def test_cancel(self, _cq, _edit):
        record = _record(status=SocialCommentReply.Status.AWAITING, draft_text="X")
        handle_reply_callback(self._callback("crno", record.pk))
        record.refresh_from_db()
        self.assertEqual(record.status, SocialCommentReply.Status.CANCELLED)

    @patch("social.services.comment_reply.answer_callback_query")
    def test_foreign_chat_rejected(self, mock_cq):
        record = _record(status=SocialCommentReply.Status.AWAITING, draft_text="X")
        handle_reply_callback(self._callback("crok", record.pk, chat="-100777"))
        record.refresh_from_db()
        self.assertEqual(record.status, SocialCommentReply.Status.AWAITING)
        self.assertIn("Чужий чат", mock_cq.call_args[0][1])

    def test_non_cr_callback_passes_through(self):
        self.assertFalse(handle_reply_callback({"id": "x", "data": "tgok:5"}))


class PlatformAdapterTests(TestCase):
    @patch("social.services.meta._graph", return_value={"id": "777"})
    def test_fb_reply_path(self, mock_graph):
        from social.services.comment_reply import _fb_reply

        result = _fb_reply("111_222", "Текст")
        self.assertTrue(result["ok"])
        args = mock_graph.call_args
        self.assertEqual(args[0][1], "111_222/comments")
        self.assertEqual(args[1]["data"]["message"], "Текст")

    @patch("social.services.meta._graph", return_value={"id": "888"})
    def test_ig_reply_path(self, mock_graph):
        from social.services.comment_reply import _ig_reply

        result = _ig_reply("555", "Текст")
        self.assertTrue(result["ok"])
        self.assertEqual(mock_graph.call_args[0][1], "555/replies")

    @patch("social.services.comment_reply._bot_token", return_value="1:ABC")
    @patch("social.services.comment_reply.requests.post")
    def test_tg_reply_path(self, mock_post, _token):
        from social.services.comment_reply import _tg_reply

        mock_post.return_value.content = b"x"
        mock_post.return_value.json.return_value = {
            "ok": True,
            "result": {"message_id": 42},
        }
        result = _tg_reply("-1004168344587", "333", "Текст")
        self.assertTrue(result["ok"])
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["reply_to_message_id"], 333)


class StoreRecordTests(TestCase):
    @patch("social.services.comment_notify.requests.post")
    @patch("social.services.comment_notify.staff_comments_configured", return_value=True)
    @patch("social.services.comment_notify._staff_target", return_value=(FAMILY_CHAT, "971"))
    @patch("social.services.comment_notify._bot_token", return_value="1:ABC")
    def test_notify_stores_reply_record(self, _t, _st, _cfg, mock_post):
        from social.services.comment_notify import InboundComment, notify_staff_comment

        mock_post.return_value.content = b"x"
        mock_post.return_value.json.return_value = {
            "ok": True,
            "result": {"message_id": 500},
        }
        comment = InboundComment(
            platform="instagram",
            text="Є доставка?",
            author_name="buyer",
            external_id="ig-c-1",
        )
        result = notify_staff_comment(comment)
        self.assertTrue(result["ok"])
        record = SocialCommentReply.objects.get()
        self.assertEqual(record.platform, "instagram")
        self.assertEqual(record.external_comment_id, "ig-c-1")
        self.assertEqual(record.alert_message_id, "500")
        self.assertEqual(record.alert_chat_id, FAMILY_CHAT)
