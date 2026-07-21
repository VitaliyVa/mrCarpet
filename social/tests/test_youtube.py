"""
Tests: YouTube token lifecycle and the resumable upload.

Two behaviours carry most of the risk and are covered first: Google silently
omitting the refresh_token, and YouTube silently forcing uploads private
before the compliance audit clears. Both answer 200 and both are invisible
unless something checks.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings

from social.models import YouTubeToken
from social.services import youtube, youtube_auth
from social.services.youtube_auth import YouTubeAuthError, get_valid_access_token

CREDS = dict(
    YOUTUBE_CLIENT_ID="cid.apps.googleusercontent.com",
    YOUTUBE_CLIENT_SECRET="GOCSPX-secret",
    YOUTUBE_REDIRECT_URI="https://mrcarpet24.com/api/youtube/callback/",
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.headers = headers or {}
        self.content = b"x"
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


def _token(**kwargs):
    from django.utils import timezone

    defaults = dict(
        access_token="acc-old",
        refresh_token="ref-old",
        channel_id="UCYssNNgxKFKEPSXRo8SDoLg",
        channel_title="mr.Carpet",
        expires_at=timezone.now() + timezone.timedelta(minutes=30),
    )
    defaults.update(kwargs)
    token = YouTubeToken.load()
    for field, value in defaults.items():
        setattr(token, field, value)
    token.save()
    return token


@override_settings(**CREDS)
class AuthorizeUrlTests(TestCase):
    def test_offline_and_consent_are_requested(self):
        """
        Without both, Google returns no refresh_token on a repeat grant and
        the integration dies an hour later looking like a server fault.
        """
        url = youtube_auth.build_authorize_url("st4te")
        self.assertIn("access_type=offline", url)
        self.assertIn("prompt=consent", url)
        self.assertIn("state=st4te", url)

    def test_only_the_upload_scope_is_requested(self):
        self.assertEqual(
            youtube_auth.SCOPES,
            ("https://www.googleapis.com/auth/youtube.upload",),
        )


@override_settings(**CREDS)
class TokenTests(TestCase):
    def test_exchange_without_refresh_token_is_rejected(self):
        """A grant with no refresh_token is useless for a scheduler."""
        payload = {"access_token": "acc", "expires_in": 3600}
        with patch.object(youtube_auth.requests, "post", return_value=FakeResponse(payload)):
            with self.assertRaises(YouTubeAuthError) as ctx:
                youtube_auth.exchange_code("code123")
        self.assertIn("refresh_token", str(ctx.exception))

    def test_refresh_keeps_the_stored_refresh_token(self):
        """Google omits it in refresh responses; overwriting would end it."""
        _token()
        payload = {"access_token": "acc-new", "expires_in": 3600}
        with patch.object(youtube_auth.requests, "post", return_value=FakeResponse(payload)):
            youtube_auth.refresh_token()

        stored = YouTubeToken.load()
        self.assertEqual(stored.access_token, "acc-new")
        self.assertEqual(stored.refresh_token, "ref-old")

    def test_failed_refresh_keeps_credentials_and_counts(self):
        _token()
        payload = {"error": "invalid_grant", "error_description": "expired"}
        with patch.object(
            youtube_auth.requests, "post", return_value=FakeResponse(payload, 400)
        ), patch.object(youtube_auth, "_warn_if_dead"):
            with self.assertRaises(YouTubeAuthError):
                youtube_auth.refresh_token()

        stored = YouTubeToken.load()
        self.assertEqual(stored.refresh_token, "ref-old")
        self.assertEqual(stored.refresh_fail_count, 1)

    def test_invalid_grant_raises_an_alert(self):
        """Testing-mode apps lose the refresh token weekly — say so."""
        _token()
        payload = {"error": "invalid_grant"}
        with patch.object(
            youtube_auth.requests, "post", return_value=FakeResponse(payload, 400)
        ), patch("social.services.comment_notify.notify_staff_text") as notify:
            with self.assertRaises(YouTubeAuthError):
                youtube_auth.refresh_token()
        self.assertTrue(notify.called)
        self.assertIn("Testing", notify.call_args.args[0])

    def test_fresh_token_is_returned_without_refresh(self):
        _token()
        with patch.object(youtube_auth.requests, "post") as post:
            self.assertEqual(get_valid_access_token(), "acc-old")
        post.assert_not_called()

    def test_expiring_token_is_refreshed(self):
        from django.utils import timezone

        _token(expires_at=timezone.now() + timezone.timedelta(seconds=30))
        payload = {"access_token": "acc-new", "expires_in": 3600}
        with patch.object(youtube_auth.requests, "post", return_value=FakeResponse(payload)):
            self.assertEqual(get_valid_access_token(), "acc-new")

    def test_unauthorized_yields_nothing(self):
        YouTubeToken.load()
        self.assertEqual(get_valid_access_token(), "")


@override_settings(**CREDS)
class UploadTests(TestCase):
    def setUp(self):
        _token()
        import tempfile

        self.tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.tmp.write(b"fake-video-bytes")
        self.tmp.close()

    def tearDown(self):
        import os

        os.unlink(self.tmp.name)

    def _upload(self, finish_payload=None, finish_status=200):
        session = FakeResponse(
            {}, 200, headers={"Location": "https://upload.example/session"}
        )
        finish = FakeResponse(
            finish_payload
            if finish_payload is not None
            else {"id": "vid123", "status": {"privacyStatus": "public"}},
            finish_status,
        )
        with patch.object(youtube.requests, "post", return_value=session) as post, \
             patch.object(youtube.requests, "put", return_value=finish) as put:
            result = youtube.upload_video(
                file_path=self.tmp.name,
                title="Скільки коштує килим?",
                description="опис",
                tags=["килими"],
                privacy="public",
            )
        return result, post, put

    def test_successful_upload_returns_a_shorts_url(self):
        result, _, _ = self._upload()
        self.assertEqual(result["external_id"], "vid123")
        self.assertIn("/shorts/vid123", result["external_url"])
        self.assertFalse(result["forced_private"])

    def test_metadata_is_sent_on_the_session_request(self):
        import json

        _, post, _ = self._upload()
        body = json.loads(post.call_args.kwargs["data"].decode())
        self.assertEqual(body["snippet"]["title"], "Скільки коштує килим?")
        self.assertEqual(body["status"]["privacyStatus"], "public")
        self.assertIs(body["status"]["selfDeclaredMadeForKids"], False)

    def test_ai_generated_content_is_declared(self):
        """Same honesty as is_aigc on TikTok — the visuals are model-made."""
        import json

        _, post, _ = self._upload()
        body = json.loads(post.call_args.kwargs["data"].decode())
        self.assertTrue(body["status"]["containsSyntheticMedia"])

    def test_forced_private_is_reported_not_swallowed(self):
        """
        Before the compliance audit YouTube answers 200 and quietly rewrites
        privacyStatus. Nothing in the response says "this failed".
        """
        result, _, _ = self._upload(
            finish_payload={"id": "vid123", "status": {"privacyStatus": "private"}}
        )
        self.assertTrue(result["forced_private"])
        self.assertEqual(result["privacy"], "private")

    def test_missing_file_is_refused_before_any_call(self):
        with patch.object(youtube.requests, "post") as post:
            with self.assertRaises(youtube.YouTubePublishError):
                youtube.upload_video(
                    file_path="/nope/missing.mp4", title="t", description="d"
                )
        post.assert_not_called()

    def test_upload_failure_is_raised(self):
        with self.assertRaises(youtube.YouTubePublishError):
            self._upload(finish_payload={"error": "quota"}, finish_status=403)

    def test_unauthorized_account_is_refused(self):
        YouTubeToken.objects.all().delete()
        with self.assertRaises(youtube.YouTubeConfigError):
            youtube.upload_video(file_path=self.tmp.name, title="t", description="d")
