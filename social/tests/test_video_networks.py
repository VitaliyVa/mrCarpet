"""
Tests: fan-out of one daily video across several networks.

The point of the delivery rows is that networks fail independently. These
tests use fake adapters rather than the real ones so the behaviour under test
is the pipeline's, not any particular API's.
"""

from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from catalog.models import Product, ProductAttribute, ProductImage, Size
from social.models import SocialSettings, TikTokDailyPick, VideoDelivery
from social.services import tiktok_publish, video_networks
from social.services.tiktok_publish import TikTokPipelineError, publish_pick
from social.services.video_networks import PublishResult

PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
)


class FakeAdapter:
    """A network that does exactly what the test tells it to."""

    needs_local_file = False

    def __init__(
        self,
        key,
        *,
        label="",
        enabled=True,
        configured=True,
        error="",
        private=False,
    ):
        self.key = key
        self.label = label or key
        self._enabled = enabled
        self._configured = configured
        self._error = error
        self._private = private
        self.calls = []

    def is_configured(self):
        return self._configured

    def is_enabled(self, social):
        return self._enabled

    def caption(self, pick, script):
        return f"caption for {self.key}"

    def publish(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise RuntimeError(self._error)
        return PublishResult(
            external_id=f"{self.key}-1",
            external_url=f"https://example.test/{self.key}",
            private=self._private,
        )


def _pick(status=TikTokDailyPick.Status.GENERATED):
    product = Product.objects.create(title="Килим тест", slug="kylym-fanout")
    ProductImage.objects.create(
        product=product,
        image=SimpleUploadedFile("s.gif", PIXEL, content_type="image/gif"),
        is_ai=True,
    )
    size = Size.objects.create(title="1.2x2.0")
    ProductAttribute.objects.create(product=product, size=size, price=2300, quantity=1)
    return TikTokDailyPick.objects.create(product=product, status=status)


class FanOutTests(TestCase):
    def setUp(self):
        social = SocialSettings.load()
        social.tiktok_auto_enabled = True
        social.save()
        self.pick = _pick()
        self.montage = "social/tiktok/final/pick-fanout.mp4"
        default_storage.save(self.montage, ContentFile(b"video-bytes"))

    def tearDown(self):
        if default_storage.exists(self.montage):
            default_storage.delete(self.montage)

    def _run(self, adapters, **kwargs):
        with patch.object(video_networks, "REGISTRY", adapters), \
             patch.object(tiktok_publish, "build_final_video", return_value=self.montage), \
             patch.object(tiktok_publish, "_notify"):
            return publish_pick(self.pick, **kwargs)

    def test_every_network_receives_the_same_video(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        ig = FakeAdapter(VideoDelivery.Platform.INSTAGRAM)
        self._run([tt, ig])

        self.assertEqual(len(tt.calls), 1)
        self.assertEqual(len(ig.calls), 1)
        self.assertEqual(tt.calls[0]["video_url"], ig.calls[0]["video_url"])
        self.assertTrue(tt.calls[0]["video_url"].startswith("https://"))

    def test_each_network_gets_its_own_caption(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        ig = FakeAdapter(VideoDelivery.Platform.INSTAGRAM)
        self._run([tt, ig])
        self.assertNotEqual(tt.calls[0]["caption"], ig.calls[0]["caption"])

    def test_one_network_failing_does_not_stop_the_others(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        ig = FakeAdapter(VideoDelivery.Platform.INSTAGRAM, error="IG is down")
        result = self._run([tt, ig])

        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.PARTIAL)
        self.assertEqual(len(result["published"]), 1)
        self.assertEqual(len(result["failed"]), 1)

        rows = {d.platform: d for d in self.pick.deliveries.all()}
        self.assertEqual(rows["tiktok"].status, VideoDelivery.Status.PUBLISHED)
        self.assertEqual(rows["instagram"].status, VideoDelivery.Status.FAILED)
        self.assertIn("IG is down", rows["instagram"].error)

    def test_private_post_is_recorded_as_such(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK, private=True)
        self._run([tt])
        row = self.pick.deliveries.get(platform="tiktok")
        self.assertEqual(row.status, VideoDelivery.Status.PUBLISHED_PRIVATE)
        self.assertTrue(row.is_success)

    def test_disabled_network_is_skipped_not_failed(self):
        """A network we never switched on must not read as a daily error."""
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        yt = FakeAdapter(VideoDelivery.Platform.YOUTUBE, enabled=False)
        result = self._run([tt, yt])

        self.assertEqual(result["failed"], [])
        self.assertEqual(len(result["skipped"]), 1)
        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.PUBLISHED)
        self.assertEqual(
            self.pick.deliveries.get(platform="youtube").status,
            VideoDelivery.Status.SKIPPED,
        )
        self.assertEqual(yt.calls, [])

    def test_unconfigured_network_is_skipped_not_failed(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        th = FakeAdapter(VideoDelivery.Platform.THREADS, configured=False)
        result = self._run([tt, th])

        self.assertEqual(result["failed"], [])
        self.assertIn("не налаштовано", result["skipped"][0])
        self.assertEqual(th.calls, [])

    def test_total_failure_raises_and_marks_the_pick(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK, error="nope")
        with self.assertRaises(TikTokPipelineError):
            self._run([tt])
        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.FAILED)


class RetryTests(TestCase):
    """
    A partial run must be resumable without double-posting.

    This is the whole reason deliveries are rows rather than a status field.
    """

    def setUp(self):
        social = SocialSettings.load()
        social.tiktok_auto_enabled = True
        social.save()
        self.pick = _pick()
        self.montage = "social/tiktok/final/pick-retry.mp4"
        default_storage.save(self.montage, ContentFile(b"video-bytes"))

    def tearDown(self):
        if default_storage.exists(self.montage):
            default_storage.delete(self.montage)

    def _run(self, adapters):
        with patch.object(video_networks, "REGISTRY", adapters), \
             patch.object(tiktok_publish, "build_final_video", return_value=self.montage), \
             patch.object(tiktok_publish, "_notify"):
            return publish_pick(self.pick)

    def test_retry_skips_networks_that_already_succeeded(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        ig_down = FakeAdapter(VideoDelivery.Platform.INSTAGRAM, error="down")
        self._run([tt, ig_down])
        self.assertEqual(len(tt.calls), 1)

        # Second run: Instagram recovered, TikTok must not be touched again.
        tt_again = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        ig_up = FakeAdapter(VideoDelivery.Platform.INSTAGRAM)
        self.pick.refresh_from_db()
        self._run([tt_again, ig_up])

        self.assertEqual(tt_again.calls, [], "TikTok was posted to twice")
        self.assertEqual(len(ig_up.calls), 1)

        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.PUBLISHED)

    def test_partial_pick_does_not_short_circuit_as_already_published(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        ig = FakeAdapter(VideoDelivery.Platform.INSTAGRAM, error="down")
        self._run([tt, ig])
        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.PARTIAL)

        result = self._run([tt, FakeAdapter(VideoDelivery.Platform.INSTAGRAM)])
        self.assertNotIn("already_published", result)

    def test_fully_published_pick_is_not_reposted(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        self._run([tt])
        self.pick.refresh_from_db()

        again = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        result = self._run([again])
        self.assertTrue(result["already_published"])
        self.assertEqual(again.calls, [])

    def test_one_delivery_row_per_network(self):
        tt = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        ig = FakeAdapter(VideoDelivery.Platform.INSTAGRAM, error="down")
        self._run([tt, ig])
        self._run([tt, FakeAdapter(VideoDelivery.Platform.INSTAGRAM)])
        self.assertEqual(self.pick.deliveries.count(), 2)


class VideoTopicTests(TestCase):
    """
    Video reports live in their own Telegram topic.

    They arrive daily and get answered on a slower rhythm than customer
    comments, so mixing the two buries the messages that need a reply.
    """

    def setUp(self):
        from project.models import TelegramSettings

        tg = TelegramSettings.load()
        tg.bot_token = "test-token"
        tg.chat_id = "-100500"
        tg.message_thread_id = "7"
        tg.save()

        social = SocialSettings.load()
        social.staff_comments_chat_id = "-100500"
        social.staff_comments_thread_id = "11"
        social.save()

    def _thread_used(self):
        from social.services import comment_notify

        with patch.object(comment_notify.requests, "post") as post:
            post.return_value.content = b"{}"
            post.return_value.json.return_value = {"ok": True, "result": {}}
            comment_notify.notify_staff_text("звіт", video=True)
        return post.call_args.kwargs["json"].get("message_thread_id")

    def test_report_goes_to_the_video_topic(self):
        social = SocialSettings.load()
        social.video_comments_thread_id = "42"
        social.save()
        self.assertEqual(self._thread_used(), 42)

    def test_unset_video_topic_falls_back_to_the_comments_topic(self):
        """A missing thread id must not send the daily report into silence."""
        self.assertEqual(self._thread_used(), 11)

    def test_video_topic_may_not_be_the_orders_topic(self):
        """The orders AI must never ingest daily video reports."""
        from social.services.tg_isolation import isolation_issues

        issues = isolation_issues(
            staff_comments_id="-100500",
            staff_comments_thread_id="11",
            video_comments_thread_id="7",
            family_id="-100500",
            orders_thread="7",
        )
        self.assertTrue(any("video_comments_thread_id" in i for i in issues))

    def test_distinct_video_topic_is_accepted(self):
        from social.services.tg_isolation import isolation_issues

        issues = isolation_issues(
            staff_comments_id="-100500",
            staff_comments_thread_id="11",
            video_comments_thread_id="42",
            family_id="-100500",
            orders_thread="7",
        )
        self.assertEqual(issues, [])

    def test_pipeline_reports_are_routed_to_the_video_topic(self):
        from social.services import comment_notify

        with patch.object(comment_notify, "notify_staff_text") as notify:
            tiktok_publish._notify("привіт")
        self.assertTrue(notify.call_args.kwargs["video"])


class CleanupTests(TestCase):
    """
    Files are removed on age, not on the first network's confirmation.

    Meta and Threads fetch asynchronously and YouTube reads the bytes off
    disk, so deleting at publish time leaves the rest fetching a 404.
    """

    def _pick_with_files(self, *, status, age_hours):
        pick = _pick(status=status)
        pick.picked_at = timezone.now() - timedelta(hours=age_hours)
        pick.video_path = default_storage.save(
            f"social/tiktok/video/clip-{pick.pk}.mp4", ContentFile(b"clip")
        )
        pick.montage_path = default_storage.save(
            f"social/tiktok/final/final-{pick.pk}.mp4", ContentFile(b"final")
        )
        pick.save()
        return pick

    def test_old_published_files_are_removed(self):
        pick = self._pick_with_files(
            status=TikTokDailyPick.Status.PUBLISHED, age_hours=48
        )
        clip, final = pick.video_path, pick.montage_path

        removed = tiktok_publish.cleanup_old_media()

        self.assertEqual(removed, 2)
        self.assertFalse(default_storage.exists(clip))
        self.assertFalse(default_storage.exists(final))
        pick.refresh_from_db()
        self.assertEqual(pick.video_path, "")
        self.assertEqual(pick.montage_path, "")

    def test_todays_files_are_left_alone(self):
        """The networks may still be fetching."""
        pick = self._pick_with_files(
            status=TikTokDailyPick.Status.PUBLISHED, age_hours=2
        )
        self.assertEqual(tiktok_publish.cleanup_old_media(), 0)
        self.assertTrue(default_storage.exists(pick.montage_path))

    def test_unpublished_picks_keep_their_files_forever(self):
        """
        The clip is the only thing standing between a retry and paying for a
        new video, so age alone must not delete it.
        """
        pick = self._pick_with_files(
            status=TikTokDailyPick.Status.GENERATED, age_hours=96
        )
        self.assertEqual(tiktok_publish.cleanup_old_media(), 0)
        self.assertTrue(default_storage.exists(pick.video_path))

    def test_partial_picks_are_cleaned_too(self):
        pick = self._pick_with_files(
            status=TikTokDailyPick.Status.PARTIAL, age_hours=48
        )
        self.assertEqual(tiktok_publish.cleanup_old_media(), 2)
        pick.refresh_from_db()
        self.assertEqual(pick.montage_path, "")
