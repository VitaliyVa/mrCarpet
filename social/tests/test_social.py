from django.test import SimpleTestCase, TestCase, override_settings
from unittest.mock import MagicMock, patch

from social.models import SocialPost, SocialSettings
from social.services.media_urls import build_caption, product_share_url
from social.services.publish import ensure_deliveries, publish_post
from social.services.telegram_products import handle_discussion_comment, _build_reply
from social.services.tiktok import _normalize_privacy, TikTokPublishError
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
        post = SocialPost.objects.create(caption="x", target_instagram=True)
        result = publish_post(post.pk)
        self.assertEqual(result.status, SocialPost.Status.FAILED)


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
