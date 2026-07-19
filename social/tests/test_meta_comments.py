"""Tests: Meta webhook — дзеркало IG/FB коментів у staff topic."""

import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from social.services import meta_comments
from social.services.meta_comments import (
    handle_meta_webhook,
    inbound_from_facebook_change,
    inbound_from_instagram_change,
    verify_signature,
)

PAGE_ID = "1245208955340257"
IG_ID = "17841443251761380"


def _fb_payload(message="Скільки коштує?", from_id="999", verb="add"):
    return {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "changes": [
                    {
                        "field": "feed",
                        "value": {
                            "item": "comment",
                            "verb": verb,
                            "comment_id": f"{PAGE_ID}_111",
                            "post_id": f"{PAGE_ID}_222",
                            "from": {"id": from_id, "name": "Тест Юзер"},
                            "message": message,
                            "created_time": 1789000000,
                        },
                    }
                ],
            }
        ],
    }


@override_settings(META_PAGE_ID=PAGE_ID, META_IG_USER_ID=IG_ID)
class FacebookParseTests(TestCase):
    def test_parses_comment(self):
        value = _fb_payload()["entry"][0]["changes"][0]["value"]
        comment = inbound_from_facebook_change(value)
        self.assertIsNotNone(comment)
        self.assertEqual(comment.platform, "facebook")
        self.assertEqual(comment.text, "Скільки коштує?")
        self.assertEqual(comment.author_name, "Тест Юзер")
        self.assertIn("facebook.com", comment.comment_url)

    def test_skips_own_page_comment(self):
        value = _fb_payload(from_id=PAGE_ID)["entry"][0]["changes"][0]["value"]
        self.assertIsNone(inbound_from_facebook_change(value))

    def test_skips_non_add_verbs(self):
        value = _fb_payload(verb="remove")["entry"][0]["changes"][0]["value"]
        self.assertIsNone(inbound_from_facebook_change(value))

    def test_skips_non_comment_items(self):
        self.assertIsNone(
            inbound_from_facebook_change({"item": "like", "verb": "add"})
        )


@override_settings(META_PAGE_ID=PAGE_ID, META_IG_USER_ID=IG_ID)
class InstagramParseTests(TestCase):
    @patch(
        "social.services.meta_comments._instagram_media_permalink",
        return_value="https://www.instagram.com/p/XYZ/",
    )
    def test_parses_comment(self, _permalink):
        comment = inbound_from_instagram_change(
            {
                "id": "555",
                "text": "Є в наявності?",
                "from": {"id": "777", "username": "buyer_ua"},
                "media": {"id": "444"},
            }
        )
        self.assertIsNotNone(comment)
        self.assertEqual(comment.platform, "instagram")
        self.assertEqual(comment.author_username, "buyer_ua")
        self.assertEqual(comment.post_url, "https://www.instagram.com/p/XYZ/")

    def test_skips_own_account_reply(self):
        self.assertIsNone(
            inbound_from_instagram_change(
                {"id": "556", "text": "Дякуємо!", "from": {"id": IG_ID}}
            )
        )


@override_settings(META_PAGE_ID=PAGE_ID, META_IG_USER_ID=IG_ID)
class HandleWebhookTests(TestCase):
    def setUp(self):
        meta_comments._seen.clear()

    @patch("social.services.meta_comments.notify_staff_comment", return_value={"ok": True})
    @patch("social.services.meta_comments.staff_comments_configured", return_value=True)
    def test_fb_comment_notifies(self, _cfg, mock_notify):
        sent = handle_meta_webhook(_fb_payload())
        self.assertEqual(sent, 1)
        mock_notify.assert_called_once()

    @patch("social.services.meta_comments.notify_staff_comment", return_value={"ok": True})
    @patch("social.services.meta_comments.staff_comments_configured", return_value=True)
    def test_duplicate_delivery_deduped(self, _cfg, mock_notify):
        handle_meta_webhook(_fb_payload())
        sent = handle_meta_webhook(_fb_payload())
        self.assertEqual(sent, 0)
        mock_notify.assert_called_once()


class SignatureTests(TestCase):
    @override_settings(META_APP_SECRET="topsecret")
    def test_valid_signature(self):
        body = b'{"object":"page"}'
        sig = "sha256=" + hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_signature(body, sig))

    @override_settings(META_APP_SECRET="topsecret")
    def test_invalid_signature(self):
        self.assertFalse(verify_signature(b"{}", "sha256=deadbeef"))

    @override_settings(META_APP_SECRET="")
    def test_no_secret_accepts_with_warning(self):
        self.assertTrue(verify_signature(b"{}", ""))


@override_settings(
    META_PAGE_ID=PAGE_ID,
    META_IG_USER_ID=IG_ID,
    META_WEBHOOK_VERIFY_TOKEN="verify-me",
    META_APP_SECRET="",
    ALLOWED_HOSTS=["testserver"],
)
class WebhookEndpointTests(TestCase):
    def setUp(self):
        meta_comments._seen.clear()
        self.client = Client()

    def test_get_verify_ok(self):
        resp = self.client.get(
            "/api/meta/webhook/",
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-me",
                "hub.challenge": "12345",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"12345")

    def test_get_verify_wrong_token(self):
        resp = self.client.get(
            "/api/meta/webhook/",
            {"hub.mode": "subscribe", "hub.verify_token": "wrong"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("social.services.meta_comments.notify_staff_comment", return_value={"ok": True})
    @patch("social.services.meta_comments.staff_comments_configured", return_value=True)
    def test_post_event_returns_200(self, _cfg, mock_notify):
        resp = self.client.post(
            "/api/meta/webhook/",
            data=json.dumps(_fb_payload()),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_notify.assert_called_once()

    def test_post_bad_json_400(self):
        resp = self.client.post(
            "/api/meta/webhook/", data="not-json", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
