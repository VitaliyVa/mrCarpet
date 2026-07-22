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


class StaggerTests(TestCase):
    """
    Five identical posts landing to the same second is the signature of a bot.
    Networks are released one at a time, and a pick is only finished once the
    last slot has come round.
    """

    def setUp(self):
        social = SocialSettings.load()
        social.tiktok_auto_enabled = True
        social.save()
        self.pick = _pick()
        self.montage = "social/tiktok/final/pick-stagger.mp4"
        default_storage.save(self.montage, ContentFile(b"video-bytes"))

    def tearDown(self):
        if default_storage.exists(self.montage):
            default_storage.delete(self.montage)

    def _run(self, adapters, **kwargs):
        with patch.object(video_networks, "REGISTRY", adapters), \
             patch.object(tiktok_publish, "build_final_video", return_value=self.montage), \
             patch.object(tiktok_publish, "_notify"):
            return publish_pick(self.pick, **kwargs)

    def _delayed(self, key, minutes, label=""):
        adapter = FakeAdapter(key, label=label or key.title())
        adapter.delay_minutes = minutes
        return adapter

    def test_first_network_goes_out_immediately(self):
        now_net = self._delayed(VideoDelivery.Platform.TIKTOK, 0)
        later = self._delayed(VideoDelivery.Platform.INSTAGRAM, 20)
        result = self._run([now_net, later])

        self.assertEqual(len(now_net.calls), 1)
        self.assertEqual(later.calls, [], "second network should still be waiting")
        self.assertEqual(len(result["waiting"]), 1)

    def test_pick_is_not_marked_published_while_a_slot_is_pending(self):
        """Marking it done would stop the retry that has to deliver the rest."""
        self._run(
            [
                self._delayed(VideoDelivery.Platform.TIKTOK, 0),
                self._delayed(VideoDelivery.Platform.INSTAGRAM, 20),
            ]
        )
        self.pick.refresh_from_db()
        self.assertNotEqual(self.pick.status, TikTokDailyPick.Status.PUBLISHED)

    def test_due_network_is_released_on_a_later_run(self):
        now_net = self._delayed(VideoDelivery.Platform.TIKTOK, 0)
        later = self._delayed(VideoDelivery.Platform.INSTAGRAM, 20)
        self._run([now_net, later])

        # Pretend the first delivery happened half an hour ago.
        row = self.pick.deliveries.get(platform="tiktok")
        row.published_at = timezone.now() - timedelta(minutes=30)
        row.save(update_fields=["published_at"])

        released = self._delayed(VideoDelivery.Platform.INSTAGRAM, 20)
        self._run([now_net, released])

        self.assertEqual(len(released.calls), 1)
        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.PUBLISHED)

    def test_force_ignores_the_stagger(self):
        """An operator clicking publish has already decided to wait for nothing."""
        later = self._delayed(VideoDelivery.Platform.INSTAGRAM, 20)
        self._run([self._delayed(VideoDelivery.Platform.TIKTOK, 0), later], force=True)
        self.assertEqual(len(later.calls), 1)

    def test_report_waits_for_the_last_network(self):
        """One message at the end, not a ticker of five."""
        with patch.object(video_networks, "REGISTRY", [
            self._delayed(VideoDelivery.Platform.TIKTOK, 0),
            self._delayed(VideoDelivery.Platform.INSTAGRAM, 20),
        ]), \
             patch.object(tiktok_publish, "build_final_video", return_value=self.montage), \
             patch.object(tiktok_publish, "_notify") as notify:
            publish_pick(self.pick)
        notify.assert_not_called()

    def test_final_report_lists_every_network_not_just_the_last(self):
        """
        Built from the delivery rows, not from what the last tick did —
        otherwise four of five would read as "already done".
        """
        first = self._delayed(VideoDelivery.Platform.TIKTOK, 0, label="TikTok")
        later = self._delayed(
            VideoDelivery.Platform.INSTAGRAM, 20, label="Instagram Reels"
        )
        self._run([first, later])

        row = self.pick.deliveries.get(platform="tiktok")
        row.published_at = timezone.now() - timedelta(minutes=30)
        row.save(update_fields=["published_at"])

        with patch.object(video_networks, "REGISTRY", [first, later]), \
             patch.object(tiktok_publish, "build_final_video", return_value=self.montage), \
             patch.object(tiktok_publish, "_notify") as notify:
            publish_pick(self.pick)

        text = notify.call_args.args[0]
        self.assertIn("TikTok", text)
        self.assertIn("Instagram Reels", text)
        self.assertNotIn("вже було", text)
        self.assertIn("опубліковано (2)", text)

    def test_first_network_failure_with_slots_pending_keeps_the_pick_alive(self):
        """
        FAILED here would kill the day: four networks were queued and the
        ticks were about to deliver them.
        """
        broken = FakeAdapter(VideoDelivery.Platform.TIKTOK, error="api down")
        broken.delay_minutes = 0
        later = self._delayed(VideoDelivery.Platform.INSTAGRAM, 20)
        self._run([broken, later])

        self.pick.refresh_from_db()
        self.assertEqual(self.pick.status, TikTokDailyPick.Status.GENERATED)

    def test_registry_delays_are_spread_out(self):
        seen = [
            (a.label, getattr(a, "delay_minutes", None))
            for a in video_networks.all_adapters()
        ]
        delays = [d for _, d in seen]
        self.assertEqual(delays[0], 0, "something must go out immediately")
        self.assertEqual(sorted(delays), delays, "delays should ascend")
        self.assertEqual(len(set(delays)), len(delays), "no two networks share a slot")


class TickGateTests(TestCase):
    """
    The ten-minute tick may CONTINUE a rollout, never begin one. When it could,
    the whole day went out right after the 04:00 generation instead of at 18:00.
    """

    def setUp(self):
        social = SocialSettings.load()
        social.tiktok_auto_enabled = True
        social.save()
        self.pick = _pick()
        self.montage = "social/tiktok/final/pick-tickgate.mp4"
        default_storage.save(self.montage, ContentFile(b"video-bytes"))

    def tearDown(self):
        if default_storage.exists(self.montage):
            default_storage.delete(self.montage)

    def test_tick_does_not_start_a_rollout(self):
        """A GENERATED pick with no delivery rows belongs to the 18:00 slot."""
        from social.management.commands.tiktok_scheduler import _publish_due

        adapter = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        adapter.delay_minutes = 0
        with patch.object(video_networks, "REGISTRY", [adapter]), \
             patch.object(tiktok_publish, "build_final_video", return_value=self.montage), \
             patch.object(tiktok_publish, "_notify"):
            out = _publish_due()

        self.assertEqual(out, "")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.pick.deliveries.exists())

    def test_tick_continues_a_started_rollout(self):
        from social.management.commands.tiktok_scheduler import _publish_due

        first = FakeAdapter(VideoDelivery.Platform.TIKTOK)
        first.delay_minutes = 0
        later = FakeAdapter(VideoDelivery.Platform.INSTAGRAM, label="Instagram Reels")
        later.delay_minutes = 20
        with patch.object(video_networks, "REGISTRY", [first, later]), \
             patch.object(tiktok_publish, "build_final_video", return_value=self.montage), \
             patch.object(tiktok_publish, "_notify"):
            publish_pick(self.pick)  # the 18:00 slot starts the rollout
            row = self.pick.deliveries.get(platform="tiktok")
            row.published_at = timezone.now() - timedelta(minutes=30)
            row.save(update_fields=["published_at"])
            out = _publish_due()

        self.assertIn("Instagram Reels", out)
        self.assertEqual(len(later.calls), 1)


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


class CaptionTests(TestCase):
    """
    Every network gets the price rule applied to how much of the caption it
    actually shows before the video is watched.
    """

    def setUp(self):
        self.pick = _pick()
        self.script = None

    def _pick_with_specs(self):
        from catalog.models import (
            ProductSpecification,
            Specification,
            SpecificationValue,
        )

        pick = self.pick
        for name, value in (
            ("Форма килима", "Овал"),
            ("Виробник", "Україна"),
            ("Основа", "Джут"),
            ("Склад килима", "Поліпропілен"),
            ("Висота ворса", "6.5 мм"),
        ):
            spec, _ = Specification.objects.get_or_create(title=name)
            val, _ = SpecificationValue.objects.get_or_create(
                specification=spec, title=value
            )
            ProductSpecification.objects.create(
                product=pick.product, specification=spec, spec_value=val
            )
        return pick

    def _caption(self, platform):
        from social.services.video_caption import build_caption

        return build_caption(self.pick, platform=platform)

    def test_feed_captions_hide_the_price_up_front(self):
        for platform in (
            VideoDelivery.Platform.TIKTOK,
            VideoDelivery.Platform.INSTAGRAM,
            VideoDelivery.Platform.FACEBOOK,
        ):
            with self.subTest(platform=platform):
                head = " ".join(self._caption(platform).splitlines()[:2])
                self.assertNotIn("2300", head)
                self.assertNotIn("грн", head)

    def test_feed_captions_still_list_the_sizes_further_down(self):
        caption = self._caption(VideoDelivery.Platform.INSTAGRAM)
        self.assertIn("2300 грн", caption)
        self.assertIn("#килими", caption)

    def test_threads_caption_omits_the_price_entirely(self):
        """
        Threads shows the whole post at once — there is no "further down" to
        hide a price in, so the size list is dropped.
        """
        caption = self._caption(VideoDelivery.Platform.THREADS)
        self.assertNotIn("2300", caption)
        self.assertNotIn("грн", caption)
        self.assertIn("Вгадали?", caption)

    def test_threads_caption_fits_the_limit(self):
        from social.services.video_caption import CAPTION_LIMITS

        caption = self._caption(VideoDelivery.Platform.THREADS)
        self.assertLessEqual(
            len(caption), CAPTION_LIMITS[VideoDelivery.Platform.THREADS]
        )

    def test_threads_keeps_hashtags_few(self):
        caption = self._caption(VideoDelivery.Platform.THREADS)
        self.assertLessEqual(caption.count("#"), 3)

    def test_facebook_caption_carries_a_clickable_link(self):
        """The one network where a caption link works — do not waste it."""
        caption = self._caption(VideoDelivery.Platform.FACEBOOK)
        self.assertIn("http", caption)

    def test_links_are_tagged_so_ga4_can_tell_networks_apart(self):
        """
        Platform metrics answer "who watched". This answers "who came and
        bought" — and it needs no permission from anyone.
        """
        from social.services.video_caption import product_url_for

        url = product_url_for(self.pick.product, VideoDelivery.Platform.FACEBOOK)
        self.assertIn("utm_source=facebook", url)
        self.assertIn("utm_medium=video", url)
        self.assertIn("utm_campaign=daily-video", url)

    def test_each_network_gets_its_own_utm_source(self):
        from social.services.video_caption import product_url_for

        sources = {
            product_url_for(self.pick.product, p).split("utm_source=")[1].split("&")[0]
            for p in (
                VideoDelivery.Platform.FACEBOOK,
                VideoDelivery.Platform.YOUTUBE,
                VideoDelivery.Platform.THREADS,
            )
        }
        self.assertEqual(len(sources), 3)

    def test_tagged_url_survives_an_existing_query_string(self):
        from social.services.video_caption import product_url_for

        with patch(
            "social.services.video_caption.build_product_content"
        ) as content:
            content.return_value.url = "https://mrcarpet24.com/p/x/?ref=1"
            url = product_url_for(self.pick.product, "threads")
        self.assertIn("?ref=1&utm_source=threads", url)

    def test_tiktok_and_instagram_captions_have_no_url(self):
        for platform in (
            VideoDelivery.Platform.TIKTOK,
            VideoDelivery.Platform.INSTAGRAM,
        ):
            with self.subTest(platform=platform):
                self.assertNotIn("https://", self._caption(platform))

    def test_youtube_title_is_the_hook_without_a_price(self):
        from social.services.video_caption import (
            YOUTUBE_TITLE_LIMIT,
            build_youtube_title,
        )

        title = build_youtube_title(self.pick)
        self.assertNotIn("2300", title)
        self.assertLessEqual(len(title), YOUTUBE_TITLE_LIMIT)
        self.assertIn("килим", title.lower())

    def test_tags_describe_this_rug_not_rugs_in_general(self):
        """
        The generic list is identical for every product, so an algorithm
        learns nothing from it. Shape, maker and backing are what a person
        actually types into a search box.
        """
        from social.services.video_caption import spec_tags

        pick = self._pick_with_specs()
        tags = spec_tags(pick.product)
        self.assertIn("овальнийкилим", tags)
        self.assertIn("українськийкилим", tags)
        self.assertIn("джутовийкилим", tags)

    def test_specific_tags_come_before_the_generic_ones(self):
        """Order decides what survives truncation — Threads keeps only one."""
        from social.services.video_caption import hashtags_for

        pick = self._pick_with_specs()
        tags = hashtags_for(pick.product, VideoDelivery.Platform.TIKTOK).split()
        self.assertLess(tags.index("#овальнийкилим"), tags.index("#килими"))

    def test_untypeable_specs_do_not_become_tags(self):
        """Nobody searches for polypropylene; a tag for it only adds noise."""
        from social.services.video_caption import spec_tags

        pick = self._pick_with_specs()
        self.assertNotIn("поліпропілен", spec_tags(pick.product))

    def test_pile_height_is_bucketed_not_copied(self):
        """"6.5 мм" is not a search term; "short pile" is."""
        from social.services.video_caption import _pile_tag

        self.assertEqual(_pile_tag("6.5 мм"), "короткийворс")
        self.assertEqual(_pile_tag("25 мм"), "довгийворс")
        self.assertEqual(_pile_tag("Безворсовий"), "")

    def test_youtube_title_carries_the_shorts_tag(self):
        """
        A 1080x1920 clip of 13s should classify as a Short on its own. The
        first real upload landed as an ordinary video, so the historical
        explicit signal is sent rather than assumed unnecessary.
        """
        from social.services.video_caption import build_youtube_title

        self.assertTrue(build_youtube_title(self.pick).endswith("#Shorts"))

    def test_long_hook_is_trimmed_to_keep_the_shorts_tag(self):
        """The tag must survive the limit — it is what makes it a Short."""
        from social.services.video_caption import (
            YOUTUBE_TITLE_LIMIT,
            build_youtube_title,
        )

        title = build_youtube_title(self.pick, {"hook": "П" * 300})
        self.assertLessEqual(len(title), YOUTUBE_TITLE_LIMIT)
        self.assertTrue(title.endswith("#Shorts"))


class CommentRoutingTests(TestCase):
    """
    Comments are routed by the post, not by the platform.

    Instagram carries both the daily Reels and the product photo carousels,
    so the platform alone cannot say which topic a comment belongs in.
    """

    def setUp(self):
        self.pick = _pick()

    def _delivery(self, platform, *, external_id="", post_id="", status=None):
        return VideoDelivery.objects.create(
            pick=self.pick,
            platform=platform,
            status=status or VideoDelivery.Status.PUBLISHED,
            external_id=external_id,
            post_id=post_id,
        )

    def test_known_reel_is_recognised(self):
        self._delivery(VideoDelivery.Platform.INSTAGRAM, external_id="ig-media-1")
        self.assertTrue(video_networks.is_video_post("ig-media-1"))

    def test_facebook_is_matched_on_the_post_id_not_the_video_id(self):
        """FB publishes against a video_id but reports comments on a post_id."""
        self._delivery(
            VideoDelivery.Platform.FACEBOOK,
            external_id="video-99",
            post_id="page_777",
        )
        self.assertTrue(video_networks.is_video_post("page_777"))
        self.assertTrue(video_networks.is_video_post("video-99"))

    def test_unrelated_post_is_not_a_video(self):
        self._delivery(VideoDelivery.Platform.INSTAGRAM, external_id="ig-media-1")
        self.assertFalse(video_networks.is_video_post("some-carousel"))

    def test_blank_id_is_not_a_video(self):
        self.assertFalse(video_networks.is_video_post(""))
        self.assertFalse(video_networks.is_video_post(None))

    def test_failed_delivery_does_not_count(self):
        self._delivery(
            VideoDelivery.Platform.INSTAGRAM,
            external_id="ig-media-1",
            status=VideoDelivery.Status.FAILED,
        )
        self.assertFalse(video_networks.is_video_post("ig-media-1"))

    def test_instagram_webhook_on_a_reel_routes_to_the_video_topic(self):
        from social.services import meta_comments

        self._delivery(VideoDelivery.Platform.INSTAGRAM, external_id="ig-media-1")
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": "c1",
                                "text": "2000?",
                                "from": {"id": "u1", "username": "buyer"},
                                "media": {"id": "ig-media-1"},
                            },
                        }
                    ]
                }
            ],
        }
        with patch.object(meta_comments, "staff_comments_configured", return_value=True), \
             patch.object(meta_comments, "_instagram_media_permalink", return_value=""), \
             patch.object(meta_comments, "notify_staff_comment",
                          return_value={"ok": True}) as notify:
            meta_comments.handle_meta_webhook(payload)

        self.assertTrue(notify.call_args.kwargs["video"])

    def test_instagram_webhook_on_a_product_post_stays_in_the_comments_topic(self):
        from social.services import meta_comments

        payload = {
            "object": "instagram",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": "c2",
                                "text": "скільки коштує?",
                                "from": {"id": "u1", "username": "buyer"},
                                "media": {"id": "carousel-7"},
                            },
                        }
                    ]
                }
            ],
        }
        with patch.object(meta_comments, "staff_comments_configured", return_value=True), \
             patch.object(meta_comments, "_instagram_media_permalink", return_value=""), \
             patch.object(meta_comments, "notify_staff_comment",
                          return_value={"ok": True}) as notify:
            meta_comments.handle_meta_webhook(payload)

        self.assertFalse(notify.call_args.kwargs["video"])


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
