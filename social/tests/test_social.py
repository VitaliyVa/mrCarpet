from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from unittest.mock import MagicMock, patch

from social.models import SocialPost, SocialPostImage, SocialSettings
from social.services.media_urls import build_caption, product_share_url
from social.services.publish import (
    ensure_deliveries,
    publish_post,
    validate_post_for_publish,
)
from social.services.telegram_products import handle_discussion_comment, _build_reply
from social.services.tg_isolation import isolation_issues, is_products_discussion_chat
from social.services.tiktok import _normalize_privacy, TikTokPublishError, publish_photos
from social.services import meta


class SocialMediaUrlTests(SimpleTestCase):
    @override_settings(SITE_URL="https://mrcarpet24.com")
    def test_share_url_with_promo(self):
        post = MagicMock()
        post.product = None
        post.utm_campaign = "rugs"
        post.promo_code = "START10"
        post.caption_for = MagicMock(return_value="Hello")
        url = product_share_url(post)
        self.assertIn("utm_campaign=rugs", url)
        self.assertIn("promo=START10", url)
        cap = build_caption(post, "instagram")
        self.assertIn("Hello", cap)
        self.assertIn("https://mrcarpet24.com", cap)


class SocialSettingsTests(TestCase):
    def test_singleton(self):
        a = SocialSettings.load()
        b = SocialSettings.load()
        self.assertEqual(a.pk, 1)
        self.assertEqual(b.pk, 1)


class SocialPublishOrchestrationTests(TestCase):
    def test_ensure_deliveries(self):
        post = SocialPost.objects.create(
            caption="test",
            target_instagram=True,
            target_facebook=True,
            target_tiktok=False,
        )
        deliveries = ensure_deliveries(post)
        platforms = {d.platform for d in deliveries}
        self.assertEqual(platforms, {"instagram", "facebook"})

    def test_publish_without_video_fails(self):
        post = SocialPost.objects.create(
            caption="x",
            media_kind=SocialPost.MediaKind.VIDEO,
            target_instagram=True,
        )
        result = publish_post(post.pk)
        self.assertEqual(result.status, SocialPost.Status.FAILED)
        self.assertIn("video", result.last_error.lower())

    def test_photos_validation_requires_images(self):
        post = SocialPost.objects.create(
            caption="gallery",
            media_kind=SocialPost.MediaKind.PHOTOS,
            target_instagram=True,
        )
        self.assertIn("image", validate_post_for_publish(post).lower())

    @override_settings(
        META_PAGE_ACCESS_TOKEN="tok",
        META_IG_USER_ID="ig1",
        META_PAGE_ID="page1",
        SITE_URL="https://mrcarpet24.com",
    )
    @patch("social.services.meta.publish_instagram_photos")
    @patch("social.services.meta.publish_facebook_page_photos")
    def test_publish_photos_fanout(self, mock_fb, mock_ig):
        mock_ig.return_value = {"external_id": "ig1", "external_url": "https://ig/p/1"}
        mock_fb.return_value = {"external_id": "fb1", "external_url": "https://fb/1"}
        post = SocialPost.objects.create(
            caption="gallery",
            media_kind=SocialPost.MediaKind.PHOTOS,
            target_instagram=True,
            target_facebook=True,
            target_tiktok=False,
        )
        tiny = SimpleUploadedFile("a.jpg", b"\xff\xd8\xff\xd9", content_type="image/jpeg")
        SocialPostImage.objects.create(post=post, image=tiny, sort_order=0)
        tiny2 = SimpleUploadedFile("b.jpg", b"\xff\xd8\xff\xd9", content_type="image/jpeg")
        SocialPostImage.objects.create(post=post, image=tiny2, sort_order=1)

        with patch(
            "social.services.publish.absolute_media_url",
            side_effect=lambda f: f"https://mrcarpet24.com/media/{getattr(f, 'name', 'x')}",
        ):
            result = publish_post(post.pk)

        self.assertEqual(result.status, SocialPost.Status.PUBLISHED)
        self.assertTrue(mock_ig.called)
        self.assertTrue(mock_fb.called)


class MetaConfigTests(SimpleTestCase):
    @override_settings(
        META_PAGE_ACCESS_TOKEN="tok", META_IG_USER_ID="1", META_PAGE_ID="2"
    )
    def test_configured(self):
        self.assertTrue(meta.meta_configured(need_ig=True, need_fb=True))

    @override_settings(META_PAGE_ACCESS_TOKEN="")
    def test_not_configured(self):
        self.assertFalse(meta.meta_configured(need_ig=True))


class TikTokPrivacyTests(TestCase):
    def test_requires_explicit_privacy(self):
        with self.assertRaises(TikTokPublishError):
            _normalize_privacy("")

    def test_forces_self_only_without_audit(self):
        SocialSettings.load()
        SocialSettings.objects.filter(pk=1).update(tiktok_audit_passed=False)
        with override_settings(TIKTOK_AUDIT_PASSED="false"):
            self.assertEqual(_normalize_privacy("PUBLIC_TO_EVERYONE"), "SELF_ONLY")


class TelegramProductsFaqTests(SimpleTestCase):
    def test_whitelist_replies(self):
        self.assertIn("Ціни", _build_reply("яка ціна?"))
        self.assertIn("Розміри", _build_reply("який розмір?"))
        self.assertIn("Наявність", _build_reply("є в наявності?"))
        self.assertIn("Доставка", _build_reply("доставка нова пошта"))
        self.assertEqual(_build_reply("привіт як справи"), "")


class TelegramProductsHandlerTests(TestCase):
    def test_handler_other_chat(self):
        SocialSettings.load()
        SocialSettings.objects.filter(pk=1).update(
            products_discussion_chat_id="-100999",
            products_bot_replies=True,
        )
        update = {
            "message": {
                "chat": {"id": -100111},
                "text": "яка ціна?",
                "message_id": 1,
            }
        }
        self.assertFalse(handle_discussion_comment(update))

    @patch("social.services.telegram_products.requests.post")
    @patch("social.services.telegram_products._bot_token", return_value="1:ABC")
    def test_handler_replies(self, _token, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        SocialSettings.load()
        SocialSettings.objects.filter(pk=1).update(
            products_discussion_chat_id="-100999",
            products_bot_replies=True,
        )
        update = {
            "message": {
                "chat": {"id": -100999},
                "text": "скільки коштує?",
                "message_id": 7,
            }
        }
        self.assertTrue(handle_discussion_comment(update))
        self.assertTrue(mock_post.called)


class MetaPublishMockTests(TestCase):
    @override_settings(
        META_PAGE_ACCESS_TOKEN="tok",
        META_IG_USER_ID="ig1",
        META_PAGE_ID="page1",
        META_GRAPH_VERSION="v21.0",
        SITE_URL="https://mrcarpet24.com",
    )
    @patch("social.services.meta._graph")
    def test_ig_reel_flow(self, mock_graph):
        mock_graph.side_effect = [
            {"id": "c1"},
            {"status_code": "FINISHED"},
            {"id": "m1"},
        ]
        result = meta.publish_instagram_reel(
            video_url="https://mrcarpet24.com/media/x.mp4",
            caption="hi",
        )
        self.assertEqual(result["external_id"], "m1")
        self.assertEqual(mock_graph.call_count, 3)

    @override_settings(
        META_PAGE_ACCESS_TOKEN="tok",
        META_IG_USER_ID="ig1",
        META_PAGE_ID="page1",
    )
    @patch("social.services.meta._graph")
    def test_ig_carousel_flow(self, mock_graph):
        mock_graph.side_effect = [
            {"id": "c1"},
            {"status_code": "FINISHED"},
            {"id": "c2"},
            {"status_code": "FINISHED"},
            {"id": "parent"},
            {"status_code": "FINISHED"},
            {"id": "m1"},
        ]
        result = meta.publish_instagram_photos(
            image_urls=[
                "https://mrcarpet24.com/a.jpg",
                "https://mrcarpet24.com/b.jpg",
            ],
            caption="hi",
        )
        self.assertEqual(result["external_id"], "m1")
        self.assertIn("/p/", result["external_url"])

    @override_settings(
        META_PAGE_ACCESS_TOKEN="tok",
        META_PAGE_ID="page1",
    )
    @patch("social.services.meta._graph")
    def test_fb_multi_photo_flow(self, mock_graph):
        mock_graph.side_effect = [
            {"id": "p1"},
            {"id": "p2"},
            {"id": "page1_99"},
        ]
        result = meta.publish_facebook_page_photos(
            image_urls=[
                "https://mrcarpet24.com/a.jpg",
                "https://mrcarpet24.com/b.jpg",
            ],
            caption="hi",
        )
        self.assertEqual(result["external_id"], "page1_99")
        self.assertEqual(mock_graph.call_count, 3)


class TgIsolationTests(TestCase):
    def test_overlap_detected(self):
        issues = isolation_issues(
            channel_id="-1001", discussion_id="-1002", family_id="-1001"
        )
        self.assertTrue(any("products_channel_id" in i for i in issues))
        issues2 = isolation_issues(
            channel_id="-1003", discussion_id="-1003", family_id="-1001"
        )
        self.assertTrue(any("discussion" in i for i in issues2))

    def test_discussion_gate(self):
        SocialSettings.load()
        SocialSettings.objects.filter(pk=1).update(
            products_discussion_chat_id="-100999"
        )
        self.assertTrue(is_products_discussion_chat(-100999))
        self.assertFalse(is_products_discussion_chat(-100111))

    @patch("project.api.telegram_webhook.handle_update_async")
    def test_webhook_never_forwards_discussion_to_ai(self, mock_ai):
        from django.test import Client

        from project.models import TelegramSettings

        SocialSettings.load()
        SocialSettings.objects.filter(pk=1).update(
            products_discussion_chat_id="-100999",
            products_bot_replies=True,
        )
        tg = TelegramSettings.load()
        tg.ai_enabled = True
        tg.bot_token = "1:ABC"
        tg.webhook_secret = "sec"
        tg.chat_id = "-100FAMILY"
        tg.save()

        client = Client()
        resp = client.post(
            "/api/telegram/webhook/",
            data=(
                b'{"message":{"chat":{"id":-100999},"text":"hello",'
                b'"message_id":1}}'
            ),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="sec",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(mock_ai.called)
        self.assertEqual(resp.json().get("handled"), "products_discussion_skip")


class TikTokPhotoPublishTests(TestCase):
    @override_settings(
        TIKTOK_ACCESS_TOKEN="tok",
        TIKTOK_OPEN_ID="oid",
        TIKTOK_AUDIT_PASSED="false",
    )
    @patch("social.services.tiktok._poll_status")
    @patch("social.services.tiktok.requests.post")
    def test_photo_init_payload(self, mock_post, mock_poll):
        SocialSettings.load()
        SocialSettings.objects.filter(pk=1).update(tiktok_audit_passed=False)
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"error": {"code": "ok"}, "data": {"publish_id": "pub1"}},
        )
        mock_poll.return_value = {"status": "PUBLISH_COMPLETE"}
        result = publish_photos(
            image_urls=["https://mrcarpet24.com/a.jpg", "https://mrcarpet24.com/b.jpg"],
            caption="hello rugs",
            privacy_level="PUBLIC_TO_EVERYONE",
            music_usage_confirmed=True,
        )
        self.assertEqual(result["privacy"], "SELF_ONLY")
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["media_type"], "PHOTO")
        self.assertEqual(payload["post_mode"], "DIRECT_POST")
        self.assertEqual(len(payload["source_info"]["photo_images"]), 2)
