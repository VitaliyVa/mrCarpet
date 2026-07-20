"""Tests: TikTok OAuth token lifecycle (24h access / 365d refresh)."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from social.models import TikTokToken
from social.services import tiktok, tiktok_auth
from social.services.tiktok_auth import (
    TikTokAuthError,
    get_valid_access_token,
    refresh_token,
)

SANDBOX = dict(
    TIKTOK_CLIENT_KEY="sbawmikcnj2shq8kdb",
    TIKTOK_CLIENT_SECRET="secret",
)


def _token(**kwargs) -> TikTokToken:
    defaults = dict(
        access_token="access-old",
        refresh_token="refresh-old",
        open_id="open-123",
        scope="user.info.basic,video.publish",
        client_key="sbawmikcnj2shq8kdb",
        expires_at=timezone.now() + timezone.timedelta(hours=20),
        refresh_expires_at=timezone.now() + timezone.timedelta(days=300),
    )
    defaults.update(kwargs)
    token = TikTokToken.load()
    for field, value in defaults.items():
        setattr(token, field, value)
    token.save()
    return token


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


@override_settings(**SANDBOX)
class RefreshTests(TestCase):
    def test_rotated_refresh_token_is_persisted(self):
        """TikTok may rotate refresh_token; keeping the old one kills the next refresh."""
        _token()
        payload = {
            "access_token": "access-new",
            "refresh_token": "refresh-NEW",
            "expires_in": 86400,
            "refresh_expires_in": 31536000,
            "open_id": "open-123",
            "scope": "user.info.basic,video.publish",
        }
        with patch.object(tiktok_auth.requests, "post", return_value=FakeResponse(payload)):
            refresh_token()

        stored = TikTokToken.load()
        self.assertEqual(stored.access_token, "access-new")
        self.assertEqual(stored.refresh_token, "refresh-NEW")
        self.assertEqual(stored.refresh_fail_count, 0)

    def test_refresh_keeps_old_refresh_token_when_absent(self):
        _token()
        payload = {"access_token": "access-new", "expires_in": 86400}
        with patch.object(tiktok_auth.requests, "post", return_value=FakeResponse(payload)):
            refresh_token()

        self.assertEqual(TikTokToken.load().refresh_token, "refresh-old")

    def test_failed_refresh_does_not_wipe_tokens(self):
        """A transient TikTok error must not destroy still-valid credentials."""
        _token()
        payload = {"error": "internal_error", "error_description": "try later"}
        with patch.object(
            tiktok_auth.requests, "post", return_value=FakeResponse(payload, 500)
        ):
            with self.assertRaises(TikTokAuthError):
                refresh_token()

        stored = TikTokToken.load()
        self.assertEqual(stored.access_token, "access-old")
        self.assertEqual(stored.refresh_token, "refresh-old")
        self.assertEqual(stored.refresh_fail_count, 1)
        self.assertIn("try later", stored.last_error)

    def test_expired_refresh_token_refuses_to_call_api(self):
        _token(refresh_expires_at=timezone.now() - timezone.timedelta(days=1))
        with patch.object(tiktok_auth.requests, "post") as post:
            with self.assertRaises(TikTokAuthError):
                refresh_token()
        post.assert_not_called()


@override_settings(**SANDBOX)
class AccessTokenTests(TestCase):
    def test_fresh_token_is_returned_without_refresh(self):
        _token(expires_at=timezone.now() + timezone.timedelta(hours=5))
        with patch.object(tiktok_auth.requests, "post") as post:
            self.assertEqual(get_valid_access_token(), "access-old")
        post.assert_not_called()

    def test_token_inside_margin_triggers_refresh(self):
        _token(expires_at=timezone.now() + timezone.timedelta(seconds=60))
        payload = {
            "access_token": "access-new",
            "refresh_token": "refresh-new",
            "expires_in": 86400,
        }
        with patch.object(tiktok_auth.requests, "post", return_value=FakeResponse(payload)):
            self.assertEqual(get_valid_access_token(), "access-new")

    def test_client_key_mismatch_is_reported_clearly(self):
        """Sandbox tokens 401 against production creds — say so instead of retrying."""
        _token(client_key="production-key")
        with self.assertRaises(TikTokAuthError) as ctx:
            get_valid_access_token()
        self.assertIn("different client_key", str(ctx.exception))

    def test_no_stored_token_returns_empty(self):
        TikTokToken.load()
        self.assertEqual(get_valid_access_token(), "")


@override_settings(**SANDBOX)
class LegacyFallbackTests(TestCase):
    @override_settings(TIKTOK_ACCESS_TOKEN="env-token", TIKTOK_OPEN_ID="env-open")
    def test_env_token_used_when_db_empty(self):
        TikTokToken.load()
        self.assertEqual(tiktok._access_token(), "env-token")
        self.assertEqual(tiktok._open_id(), "env-open")
        self.assertTrue(tiktok.tiktok_configured())

    def test_db_token_wins_over_env(self):
        _token(expires_at=timezone.now() + timezone.timedelta(hours=5))
        with override_settings(TIKTOK_ACCESS_TOKEN="env-token", TIKTOK_OPEN_ID="env-open"):
            self.assertEqual(tiktok._access_token(), "access-old")
            self.assertEqual(tiktok._open_id(), "open-123")

    def test_refresh_failure_falls_back_to_env_instead_of_raising(self):
        """publish_* must not explode on a token problem — _headers() reports it."""
        _token(expires_at=timezone.now() - timezone.timedelta(minutes=1))
        payload = {"error": "invalid_grant"}
        with patch.object(
            tiktok_auth.requests, "post", return_value=FakeResponse(payload, 400)
        ):
            with override_settings(TIKTOK_ACCESS_TOKEN="env-token"):
                self.assertEqual(tiktok._access_token(), "env-token")


@override_settings(**SANDBOX)
class AuthorizeUrlTests(TestCase):
    def test_url_carries_state_and_scopes(self):
        url = tiktok_auth.build_authorize_url("st4te")
        self.assertIn("https://www.tiktok.com/v2/auth/authorize/", url)
        self.assertIn("client_key=sbawmikcnj2shq8kdb", url)
        self.assertIn("response_type=code", url)
        self.assertIn("state=st4te", url)
        self.assertIn("video.publish", url)

    def test_sandbox_detected_from_key_prefix(self):
        self.assertTrue(tiktok_auth.is_sandbox())
        with override_settings(TIKTOK_CLIENT_KEY="awx123"):
            self.assertFalse(tiktok_auth.is_sandbox())
