"""Tests: the daily TikTok publishing pipeline."""

from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from catalog.models import Product, ProductAttribute, ProductImage, Size
from social.models import SocialSettings, TikTokDailyPick
from social.services import tiktok_publish
from social.services.tiktok_publish import TikTokPipelineError, publish_pick

PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
)


def _pick(status=TikTokDailyPick.Status.GENERATED):
    product = Product.objects.create(title="Килим тест", slug="kylym-test")
    ProductImage.objects.create(
        product=product,
        image=SimpleUploadedFile("s.gif", PIXEL, content_type="image/gif"),
        is_ai=True,
    )
    size = Size.objects.create(title="1.2x2.0")
    ProductAttribute.objects.create(product=product, size=size, price=2300, quantity=1)
    return TikTokDailyPick.objects.create(product=product, status=status)


def _enable():
    social = SocialSettings.load()
    social.tiktok_auto_enabled = True
    social.save()


class GuardTests(TestCase):
    def test_disabled_toggle_blocks_publishing(self):
        pick = _pick()
        with self.assertRaises(TikTokPipelineError):
            publish_pick(pick)

    def test_force_bypasses_the_toggle(self):
        pick = _pick()
        with patch.object(tiktok_publish, "build_final_video", side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                publish_pick(pick, force=True)

    def test_pick_without_product_is_rejected(self):
        _enable()
        pick = TikTokDailyPick.objects.create(product=None)
        with self.assertRaises(TikTokPipelineError):
            publish_pick(pick)

    def test_already_published_pick_is_not_reposted(self):
        """A retried cron must not publish the same product twice."""
        _enable()
        pick = _pick(status=TikTokDailyPick.Status.PUBLISHED)
        with patch.object(tiktok_publish, "build_final_video") as build:
            result = publish_pick(pick)
        build.assert_not_called()
        self.assertTrue(result["already_published"])


class PublishTests(TestCase):
    def setUp(self):
        _enable()
        self.pick = _pick()
        self.montage = "social/tiktok/final/pick-test.mp4"
        default_storage.save(self.montage, ContentFile(b"video-bytes"))
        self.pick.video_path = default_storage.save(
            "social/tiktok/video/clip-test.mp4", ContentFile(b"clip-bytes")
        )
        self.pick.save()

    def tearDown(self):
        for path in (self.montage, self.pick.video_path):
            if path and default_storage.exists(path):
                default_storage.delete(path)

    def _publish(self, **overrides):
        defaults = dict(
            build=self.montage,
            options=["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
            audited=False,
            result={"external_id": "v123", "privacy": "SELF_ONLY"},
        )
        defaults.update(overrides)
        with patch.object(tiktok_publish, "build_final_video", return_value=defaults["build"]), \
             patch.object(tiktok_publish.tiktok, "creator_privacy_options",
                          return_value=defaults["options"]), \
             patch.object(tiktok_publish.tiktok, "audit_passed",
                          return_value=defaults["audited"]), \
             patch.object(tiktok_publish.tiktok, "publish_video",
                          return_value=defaults["result"]) as publish, \
             patch.object(tiktok_publish, "_notify"):
            publish_pick(self.pick)
        return publish

    def test_unaudited_posts_are_forced_private(self):
        publish = self._publish()
        self.assertEqual(publish.call_args.kwargs["privacy_level"], "SELF_ONLY")

    def test_audited_account_posts_publicly(self):
        publish = self._publish(audited=True)
        self.assertEqual(publish.call_args.kwargs["privacy_level"], "PUBLIC_TO_EVERYONE")

    def test_privacy_falls_back_to_a_supported_option(self):
        """The account offers no FOLLOWER_OF_CREATOR; never send what it lacks."""
        publish = self._publish(audited=True, options=["MUTUAL_FOLLOW_FRIENDS"])
        self.assertEqual(
            publish.call_args.kwargs["privacy_level"], "MUTUAL_FOLLOW_FRIENDS"
        )

    def test_video_is_declared_as_ai_generated(self):
        publish = self._publish()
        self.assertTrue(publish.call_args.kwargs["made_with_ai"])

    def test_music_usage_is_confirmed(self):
        publish = self._publish()
        self.assertTrue(publish.call_args.kwargs["music_usage_confirmed"])

    def test_pull_url_is_public_https(self):
        publish = self._publish()
        url = publish.call_args.kwargs["video_url"]
        self.assertTrue(url.startswith("https://"))
        self.assertIn(self.montage, url)

    def test_caption_does_not_spoil_the_price_up_front(self):
        """
        TikTok shows the opening lines under the video before it is watched, so
        a price near the top answers the question the video just asked.
        """
        publish = self._publish()
        caption = publish.call_args.kwargs["caption"]
        head = " ".join(caption.splitlines()[:2])
        self.assertNotIn("2300", head)
        self.assertNotIn("грн", head)

    def test_caption_still_lists_sizes_and_hashtags(self):
        publish = self._publish()
        caption = publish.call_args.kwargs["caption"]
        self.assertIn("Розміри та ціни", caption)
        self.assertIn("2300 грн", caption)
        self.assertIn("#килими", caption)

    def test_caption_carries_no_clickable_url(self):
        """TikTok captions are not clickable; buyers go through the bio."""
        publish = self._publish()
        self.assertNotIn("https://", publish.call_args.kwargs["caption"])

    def test_files_are_removed_only_after_tiktok_confirms(self):
        montage = self.montage
        clip = self.pick.video_path
        self._publish()
        self.assertFalse(default_storage.exists(montage))
        self.assertFalse(default_storage.exists(clip))
        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.PUBLISHED)
        self.assertEqual(self.pick.video_path, "")

    def test_failure_keeps_the_files_and_marks_the_pick(self):
        """A 04:00 failure must leave something to diagnose in the morning."""
        with patch.object(tiktok_publish, "build_final_video", return_value=self.montage), \
             patch.object(tiktok_publish.tiktok, "creator_privacy_options",
                          return_value=["SELF_ONLY"]), \
             patch.object(tiktok_publish.tiktok, "audit_passed", return_value=False), \
             patch.object(tiktok_publish.tiktok, "publish_video",
                          side_effect=RuntimeError("TikTok said no")), \
             patch.object(tiktok_publish, "_notify") as notify:
            with self.assertRaises(RuntimeError):
                publish_pick(self.pick)

        self.assertTrue(default_storage.exists(self.montage))
        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.FAILED)
        self.assertIn("TikTok said no", self.pick.error)
        self.assertIn("не вийшов", notify.call_args.args[0])

    def test_failed_pick_stays_eligible_for_the_cycle(self):
        from social.services.tiktok_rotation import remaining_products

        with patch.object(tiktok_publish, "build_final_video", side_effect=RuntimeError("x")), \
             patch.object(tiktok_publish, "_notify"):
            with self.assertRaises(RuntimeError):
                publish_pick(self.pick)
        self.assertIn(
            self.pick.product_id, remaining_products().values_list("pk", flat=True)
        )


class RetryCostTests(TestCase):
    """
    A publish that TikTok rejected must be retryable for free.

    Conflating "force" with "regenerate" once paid for four videos where one
    was needed: every retry re-rendered the clip.
    """

    def setUp(self):
        _enable()
        self.pick = _pick()
        self.pick.video_path = default_storage.save(
            "social/tiktok/video/clip-retry.mp4", ContentFile(b"clip")
        )
        self.pick.save()

    def tearDown(self):
        if self.pick.video_path and default_storage.exists(self.pick.video_path):
            default_storage.delete(self.pick.video_path)

    def test_existing_clip_is_reused(self):
        from social.services.tiktok_publish import build_final_video

        with patch.object(tiktok_publish, "generate_video_for_pick") as generate, \
             patch.object(tiktok_publish, "ffmpeg_available", return_value=True), \
             patch.object(tiktok_publish, "build_montage"), \
             patch.object(tiktok_publish, "build_script", return_value={}), \
             patch.object(tiktok_publish, "pick_track", return_value=""), \
             patch("pathlib.Path.exists", return_value=True):
            build_final_video(self.pick)
        generate.assert_not_called()

    def test_regenerate_buys_a_new_clip(self):
        from social.services.tiktok_publish import build_final_video

        with patch.object(tiktok_publish, "generate_video_for_pick") as generate, \
             patch.object(tiktok_publish, "ffmpeg_available", return_value=True), \
             patch.object(tiktok_publish, "build_montage"), \
             patch.object(tiktok_publish, "build_script", return_value={}), \
             patch.object(tiktok_publish, "pick_track", return_value=""), \
             patch("pathlib.Path.exists", return_value=True):
            build_final_video(self.pick, regenerate=True)
        generate.assert_called_once()

    def test_force_publish_does_not_regenerate(self):
        """--force bypasses the guards; it must not reach for the wallet."""
        with patch.object(tiktok_publish, "build_final_video") as build, \
             patch.object(tiktok_publish.tiktok, "creator_privacy_options",
                          return_value=["SELF_ONLY"]), \
             patch.object(tiktok_publish.tiktok, "audit_passed", return_value=False), \
             patch.object(tiktok_publish.tiktok, "publish_video",
                          return_value={"external_id": "x", "privacy": "SELF_ONLY"}), \
             patch.object(tiktok_publish, "_notify"):
            build.return_value = "social/tiktok/final/x.mp4"
            publish_pick(self.pick, force=True)
        self.assertFalse(build.call_args.kwargs["regenerate"])


class SchedulerTests(TestCase):
    """The daemon must pick the right next slot across a day boundary."""

    def _next(self, hour, minute=0):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from social.management.commands.tiktok_scheduler import next_run

        now = datetime(2026, 7, 20, hour, minute, tzinfo=ZoneInfo("Europe/Kyiv"))
        moment, action = next_run(now)
        return moment.hour, action

    def test_before_dawn_goes_to_generate(self):
        self.assertEqual(self._next(2), (4, "generate"))

    def test_after_generation_goes_to_publish(self):
        self.assertEqual(self._next(9), (18, "publish"))

    def test_after_publishing_wraps_to_tomorrow(self):
        self.assertEqual(self._next(20), (4, "generate"))

    def test_exactly_on_the_hour_does_not_refire(self):
        """A slot already reached must not be scheduled again for now."""
        self.assertEqual(self._next(4, 0), (18, "publish"))


class CoverAndLabelTests(TestCase):
    """The thumbnail and the AI label are what the feed shows before a tap."""

    def setUp(self):
        _enable()
        self.pick = _pick()
        self.pick.video_path = default_storage.save(
            "social/tiktok/video/clip-cover.mp4", ContentFile(b"clip")
        )
        self.pick.save()

    def tearDown(self):
        if self.pick.video_path and default_storage.exists(self.pick.video_path):
            default_storage.delete(self.pick.video_path)

    def _publish(self):
        with patch.object(tiktok_publish, "build_final_video",
                          return_value="social/tiktok/final/x.mp4"), \
             patch.object(tiktok_publish.tiktok, "creator_privacy_options",
                          return_value=["SELF_ONLY"]), \
             patch.object(tiktok_publish.tiktok, "audit_passed", return_value=False), \
             patch.object(tiktok_publish.tiktok, "publish_video",
                          return_value={"external_id": "x", "privacy": "SELF_ONLY"}) as pub, \
             patch.object(tiktok_publish, "_notify"):
            publish_pick(self.pick)
        return pub

    def test_cover_lands_after_the_question_and_before_the_countdown(self):
        from social.services import tiktok_montage as montage

        ms = self._publish().call_args.kwargs["cover_timestamp_ms"]
        self.assertGreater(ms / 1000, 0.55)  # question has faded in
        self.assertLess(ms / 1000, montage.COUNT_START)  # no digit yet

    def test_ai_label_is_requested(self):
        self.assertTrue(self._publish().call_args.kwargs["made_with_ai"])
