"""
Tests: Threads token lifecycle and post shape.

Threads differs from TikTok in two ways that break naive code, and both are
covered here: there is no refresh_token, and a token may not be refreshed
during its first 24 hours.
"""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import (
    Product,
    ProductAttribute,
    ProductCategory,
    ProductImage,
    Size,
)
from social.models import ThreadsToken, TikTokDailyPick, VideoDelivery
from social.services import threads, threads_auth
from social.services.threads_auth import ThreadsAuthError, get_valid_access_token

PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
)

CREDS = dict(THREADS_APP_ID="th-app", THREADS_APP_SECRET="th-secret")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"x"
        self.text = str(payload)

    def json(self):
        return self._payload


def _token(**kwargs) -> ThreadsToken:
    now = timezone.now()
    defaults = dict(
        access_token="tok-old",
        user_id="th-user-1",
        username="mr.carpet",
        issued_at=now - timezone.timedelta(days=40),
        expires_at=now + timezone.timedelta(days=20),
    )
    defaults.update(kwargs)
    token = ThreadsToken.load()
    for field, value in defaults.items():
        setattr(token, field, value)
    token.save()
    return token


@override_settings(**CREDS)
class TokenLifecycleTests(TestCase):
    def test_refresh_is_refused_in_the_first_24_hours(self):
        """
        Meta rejects it anyway, and a naive "refresh every night" would hit
        this on day one and look like broken credentials.
        """
        _token(issued_at=timezone.now() - timezone.timedelta(hours=3))
        with patch.object(threads_auth.requests, "get") as get:
            with self.assertRaises(ThreadsAuthError) as ctx:
                threads_auth.refresh_token()
        get.assert_not_called()
        self.assertIn("24h", str(ctx.exception))

    def test_refresh_extends_the_token(self):
        _token()
        payload = {"access_token": "tok-new", "expires_in": 5184000}
        with patch.object(threads_auth.requests, "get", return_value=FakeResponse(payload)):
            token = threads_auth.refresh_token()

        self.assertEqual(token.access_token, "tok-new")
        self.assertGreater(token.days_until_expiry, 50)
        self.assertIsNotNone(token.last_refreshed_at)
        self.assertEqual(token.refresh_fail_count, 0)

    def test_failed_refresh_keeps_the_old_token(self):
        _token()
        with patch.object(
            threads_auth.requests,
            "get",
            return_value=FakeResponse({"error": {"message": "nope"}}, 400),
        ):
            with self.assertRaises(ThreadsAuthError):
                threads_auth.refresh_token()

        stored = ThreadsToken.load()
        self.assertEqual(stored.access_token, "tok-old")
        self.assertEqual(stored.refresh_fail_count, 1)
        self.assertIn("nope", stored.last_error)

    def test_expired_token_refuses_to_call_the_api(self):
        _token(expires_at=timezone.now() - timezone.timedelta(days=1))
        with patch.object(threads_auth.requests, "get") as get:
            with self.assertRaises(ThreadsAuthError):
                threads_auth.refresh_token()
        get.assert_not_called()

    def test_fresh_token_is_returned_without_refreshing(self):
        _token(expires_at=timezone.now() + timezone.timedelta(days=55))
        with patch.object(threads_auth.requests, "get") as get:
            self.assertEqual(get_valid_access_token(), "tok-old")
        get.assert_not_called()

    def test_token_near_expiry_is_refreshed(self):
        _token(expires_at=timezone.now() + timezone.timedelta(days=5))
        payload = {"access_token": "tok-new", "expires_in": 5184000}
        with patch.object(threads_auth.requests, "get", return_value=FakeResponse(payload)):
            self.assertEqual(get_valid_access_token(), "tok-new")

    def test_expired_token_yields_nothing_usable(self):
        _token(expires_at=timezone.now() - timezone.timedelta(days=1))
        self.assertEqual(get_valid_access_token(), "")

    def test_refresh_failure_falls_back_to_the_existing_token(self):
        """Still valid today — the warning chases a human instead."""
        _token(expires_at=timezone.now() + timezone.timedelta(days=5))
        with patch.object(
            threads_auth.requests,
            "get",
            return_value=FakeResponse({"error": "boom"}, 500),
        ):
            self.assertEqual(get_valid_access_token(), "tok-old")

    def test_unauthorized_token_yields_nothing(self):
        ThreadsToken.load()
        self.assertEqual(get_valid_access_token(), "")

    def test_authorize_url_uses_the_threads_host_and_scopes(self):
        url = threads_auth.build_authorize_url("st4te")
        self.assertIn("threads.net/oauth/authorize", url)
        self.assertIn("client_id=th-app", url)
        self.assertIn("threads_content_publish", url)
        self.assertIn("state=st4te", url)


class ProductMixin:
    def _pick(self, *, category=""):
        product = Product.objects.create(title="Килим тест", slug="kylym-threads")
        ProductImage.objects.create(
            product=product,
            image=SimpleUploadedFile("s.gif", PIXEL, content_type="image/gif"),
            is_ai=True,
        )
        size = Size.objects.create(title="1.2x2.0")
        ProductAttribute.objects.create(product=product, size=size, price=2300, quantity=1)
        if category:
            cat = ProductCategory.objects.create(title=category, slug="cat-threads")
            product.categories.add(cat)
        return TikTokDailyPick.objects.create(product=product)


class TopicTagTests(ProductMixin, TestCase):
    """
    Threads allows exactly one topic tag, and it travels as its own parameter.

    Documented, not folklore: "Only one topic tag is allowed per post". Inline
    "#" still works but Meta keeps it only for backwards compatibility.
    """

    def test_a_single_tag_is_returned(self):
        from social.services.video_caption import threads_topic_tag

        tag = threads_topic_tag(self._pick().product)
        self.assertTrue(tag)
        self.assertNotIn("#", tag)
        self.assertNotIn(" ", tag)

    def test_the_category_tag_wins_over_the_generic_ones(self):
        """A topic tag is how a community finds the post, so be specific."""
        from social.services.video_caption import threads_topic_tag

        pick = self._pick(category="В дитячу")
        self.assertEqual(threads_topic_tag(pick.product), "килимвдитячу")

    def test_tag_has_no_characters_meta_rejects(self):
        from social.services.video_caption import threads_topic_tag

        tag = threads_topic_tag(self._pick().product)
        self.assertNotIn(".", tag)
        self.assertNotIn("&", tag)
        self.assertFalse(tag.isdigit())
        self.assertLessEqual(len(tag), 50)

    def test_threads_caption_carries_no_inline_hashtags(self):
        from social.services.video_caption import build_caption

        caption = build_caption(self._pick(), platform=VideoDelivery.Platform.THREADS)
        self.assertNotIn("#", caption)

    def test_caption_fits_both_the_character_and_byte_budget(self):
        """
        Meta documents 500 characters but counts some content in bytes, and
        Cyrillic is two bytes per character. Respecting both is free here.
        """
        from social.services.video_caption import CAPTION_LIMITS, build_caption

        limit = CAPTION_LIMITS[VideoDelivery.Platform.THREADS]
        caption = build_caption(self._pick(), platform=VideoDelivery.Platform.THREADS)
        self.assertLessEqual(len(caption), limit)
        self.assertLessEqual(len(caption.encode("utf-8")), limit)


class PublishTests(ProductMixin, TestCase):
    def setUp(self):
        _token()
        self.pick = self._pick()

    def test_publish_sends_the_topic_tag_as_a_parameter(self):
        calls = []

        def fake_call(method, path, params):
            calls.append((method, path, params))
            if path.endswith("/threads"):
                return {"id": "container-1"}
            if "threads_publish" in path:
                return {"id": "post-1"}
            return {"status": "FINISHED", "permalink": "https://threads.net/p/1"}

        with patch.object(threads, "_call", side_effect=fake_call):
            result = threads.publish_video(
                video_url="https://mrcarpet24.com/m/v.mp4",
                text="текст",
                topic_tag="килими",
            )

        create = next(c for c in calls if c[1].endswith("/threads"))
        self.assertEqual(create[2]["topic_tag"], "килими")
        self.assertEqual(create[2]["media_type"], "VIDEO")
        self.assertEqual(result["external_id"], "post-1")

    def test_publish_requires_https(self):
        with self.assertRaises(threads.ThreadsPublishError):
            threads.publish_video(video_url="http://x/v.mp4", text="t")

    def test_container_error_is_reported_not_published(self):
        def fake_call(method, path, params):
            if path.endswith("/threads"):
                return {"id": "container-1"}
            if "threads_publish" in path:
                raise AssertionError("must not publish a failed container")
            return {"status": "ERROR", "error_message": "bad codec"}

        with patch.object(threads, "_call", side_effect=fake_call), \
             patch.object(threads.time, "sleep"):
            with self.assertRaises(threads.ThreadsPublishError) as ctx:
                threads.publish_video(video_url="https://x/v.mp4", text="t")
        self.assertIn("bad codec", str(ctx.exception))
