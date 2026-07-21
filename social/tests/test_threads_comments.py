"""
Tests: inbound Threads replies → staff video topic.

The format asks viewers to guess a price in the replies, so this path is not
a nicety — a network we post to but never read from is worse than one we
skip entirely.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from social.models import ThreadsToken
from social.services import threads_comments
from social.services.threads_comments import (
    handle_threads_webhook,
    inbound_from_threads_reply,
    verify_signature,
)

SECRET = "th-secret"


def _token(**kwargs):
    defaults = dict(
        access_token="tok",
        user_id="27592315127061581",
        username="mr.carpet.shop",
        issued_at=timezone.now(),
        expires_at=timezone.now() + timezone.timedelta(days=60),
    )
    defaults.update(kwargs)
    token = ThreadsToken.load()
    for field, value in defaults.items():
        setattr(token, field, value)
    token.save()
    return token


def _reply_value(**overrides):
    value = {
        "id": "8901234",
        "username": "buyer_one",
        "owner_id": "999",
        "text": "2000 грн?",
        "media_type": "TEXT_POST",
        "permalink": "https://www.threads.net/@buyer_one/post/Pp",
        "replied_to": {"id": "567890"},
        "root_post": {
            "id": "123456",
            "owner_id": "27592315127061581",
            "shortcode": "Rr",
        },
        "timestamp": "2026-07-21T10:33:16+0000",
    }
    value.update(overrides)
    return value


def _payload(value=None, field="replies"):
    return {
        "app_id": "1394760422565420",
        "topic": "moderate",
        "values": {"field": field, "value": value if value is not None else _reply_value()},
    }


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@override_settings(THREADS_APP_SECRET=SECRET)
class ParsingTests(TestCase):
    def setUp(self):
        _token()
        threads_comments._seen.clear()

    def test_reply_is_parsed(self):
        comment = inbound_from_threads_reply(_reply_value())
        self.assertEqual(comment.platform, "threads")
        self.assertEqual(comment.text, "2000 грн?")
        self.assertEqual(comment.author_username, "buyer_one")
        self.assertEqual(comment.external_id, "8901234")
        self.assertEqual(comment.parent_post_id, "123456")
        self.assertIn("threads.net", comment.comment_url)

    def test_our_own_reply_is_ignored_by_user_id(self):
        """Answering a customer must not bounce back as a new question."""
        value = _reply_value(owner_id="27592315127061581", username="mr.carpet.shop")
        self.assertIsNone(inbound_from_threads_reply(value))

    def test_our_own_reply_is_ignored_by_username(self):
        """The payload carries no is_reply_owned_by_me, so identity is compared."""
        value = _reply_value(owner_id="", username="MR.Carpet.Shop")
        self.assertIsNone(inbound_from_threads_reply(value))

    def test_empty_text_is_ignored(self):
        self.assertIsNone(inbound_from_threads_reply(_reply_value(text="   ")))

    def test_timestamp_is_parsed(self):
        comment = inbound_from_threads_reply(_reply_value())
        self.assertIsNotNone(comment.created_at)
        self.assertEqual(comment.created_at.year, 2026)

    def test_unparsable_timestamp_does_not_break_the_alert(self):
        comment = inbound_from_threads_reply(_reply_value(timestamp="not-a-date"))
        self.assertIsNotNone(comment)
        self.assertIsNone(comment.created_at)


@override_settings(THREADS_APP_SECRET=SECRET)
class RoutingTests(TestCase):
    def setUp(self):
        _token()
        threads_comments._seen.clear()

    def test_reply_goes_to_the_video_topic(self):
        """Everything we publish to Threads is a daily video."""
        with patch.object(threads_comments, "staff_comments_configured", return_value=True), \
             patch.object(threads_comments, "notify_staff_comment",
                          return_value={"ok": True}) as notify:
            sent = handle_threads_webhook(_payload())

        self.assertEqual(sent, 1)
        self.assertTrue(notify.call_args.kwargs["video"])

    def test_duplicate_delivery_is_dropped(self):
        """Meta does not promise exactly-once delivery."""
        with patch.object(threads_comments, "staff_comments_configured", return_value=True), \
             patch.object(threads_comments, "notify_staff_comment",
                          return_value={"ok": True}) as notify:
            handle_threads_webhook(_payload())
            handle_threads_webhook(_payload())

        self.assertEqual(notify.call_count, 1)

    def test_duplicate_is_dropped_after_a_restart(self):
        """The in-process cache dies on redeploy; the database check does not."""
        from social.models import SocialCommentReply

        SocialCommentReply.objects.create(
            platform="threads",
            external_comment_id="8901234",
            comment_text="2000 грн?",
            alert_chat_id="-100500",
            alert_message_id="1",
        )
        threads_comments._seen.clear()

        with patch.object(threads_comments, "staff_comments_configured", return_value=True), \
             patch.object(threads_comments, "notify_staff_comment") as notify:
            sent = handle_threads_webhook(_payload())

        self.assertEqual(sent, 0)
        notify.assert_not_called()

    def test_other_fields_are_ignored(self):
        with patch.object(threads_comments, "notify_staff_comment") as notify:
            self.assertEqual(handle_threads_webhook(_payload(field="mentions")), 0)
        notify.assert_not_called()

    def test_values_as_a_list_is_accepted(self):
        payload = {
            "topic": "moderate",
            "values": [{"field": "replies", "value": _reply_value()}],
        }
        with patch.object(threads_comments, "staff_comments_configured", return_value=True), \
             patch.object(threads_comments, "notify_staff_comment",
                          return_value={"ok": True}):
            self.assertEqual(handle_threads_webhook(payload), 1)

    def test_empty_payload_is_safe(self):
        self.assertEqual(handle_threads_webhook({}), 0)


@override_settings(
    THREADS_APP_SECRET=SECRET, THREADS_WEBHOOK_VERIFY_TOKEN="verify-me"
)
class WebhookHttpTests(TestCase):
    def setUp(self):
        _token()
        threads_comments._seen.clear()

    def test_subscription_handshake(self):
        resp = self.client.get(
            "/api/threads/webhook/",
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-me",
                "hub.challenge": "chal123",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode(), "chal123")

    def test_handshake_with_wrong_token_is_refused(self):
        resp = self.client.get(
            "/api/threads/webhook/",
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "nope",
                "hub.challenge": "chal123",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_signed_post_is_accepted(self):
        body = json.dumps(_payload()).encode()
        with patch.object(threads_comments, "staff_comments_configured", return_value=True), \
             patch.object(threads_comments, "notify_staff_comment",
                          return_value={"ok": True}) as notify:
            resp = self.client.post(
                "/api/threads/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=_sign(body),
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(notify.call_count, 1)

    def test_forged_signature_is_refused(self):
        body = json.dumps(_payload()).encode()
        with patch.object(threads_comments, "notify_staff_comment") as notify:
            resp = self.client.post(
                "/api/threads/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=_sign(body, "wrong-secret"),
            )
        self.assertEqual(resp.status_code, 403)
        notify.assert_not_called()

    def test_handler_failure_still_answers_200(self):
        """A non-200 gets retried and eventually unsubscribes the webhook."""
        body = json.dumps(_payload()).encode()
        with patch.object(
            threads_comments, "staff_comments_configured", side_effect=RuntimeError("boom")
        ):
            resp = self.client.post(
                "/api/threads/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=_sign(body),
            )
        self.assertEqual(resp.status_code, 200)

    def test_signature_uses_the_threads_secret_not_the_meta_one(self):
        """The two apps share a dashboard but not their keys."""
        body = b'{"x":1}'
        self.assertTrue(verify_signature(body, _sign(body, SECRET)))
        self.assertFalse(verify_signature(body, _sign(body, "meta-secret")))
