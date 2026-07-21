"""
Tests: daily readings of how the published videos are doing.

The parts that carry risk: not confusing "reported zero" with "will not say",
not double-counting cumulative counters, and not letting one dead network cost
the others their reading.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from social.models import TikTokDailyPick, VideoDelivery, VideoMetric
from social.services import video_metrics
from social.services.video_metrics import (
    collect_once,
    due_deliveries,
    format_summary,
    weekly_summary,
)


def _delivery(platform="youtube", external_id="vid1", days_ago=0, status="published"):
    pick = TikTokDailyPick.objects.create()
    return VideoDelivery.objects.create(
        pick=pick,
        platform=platform,
        status=status,
        external_id=external_id,
        published_at=timezone.now() - timezone.timedelta(days=days_ago),
    )


class DueTests(TestCase):
    def test_only_recent_successes_are_read(self):
        _delivery(external_id="fresh", days_ago=1)
        _delivery(external_id="stale", days_ago=30)
        _delivery(external_id="failed", days_ago=1, status="failed")
        ids = {d.external_id for d in due_deliveries()}
        self.assertEqual(ids, {"fresh"})

    def test_delivery_without_an_id_is_skipped(self):
        """A skipped network has no id to ask about."""
        _delivery(external_id="", days_ago=1)
        self.assertEqual(due_deliveries(), [])


class CollectTests(TestCase):
    def test_youtube_counters_are_stored(self):
        d = _delivery(platform="youtube", external_id="yt1")
        with patch.object(
            video_metrics, "fetch_for", return_value={"views": 12, "likes": 3, "comments": 1}
        ):
            self.assertEqual(collect_once(), 1)

        metric = VideoMetric.objects.get(delivery=d)
        self.assertEqual(metric.views, 12)
        self.assertEqual(metric.likes, 3)

    def test_running_twice_updates_rather_than_duplicates(self):
        """The scheduler ticks often; a restart must not double the table."""
        d = _delivery()
        with patch.object(
            video_metrics, "fetch_for", return_value={"views": 5, "likes": 0, "comments": 0}
        ):
            collect_once()
        with patch.object(
            video_metrics, "fetch_for", return_value={"views": 9, "likes": 0, "comments": 0}
        ):
            collect_once()

        self.assertEqual(VideoMetric.objects.filter(delivery=d).count(), 1)
        self.assertEqual(VideoMetric.objects.get(delivery=d).views, 9)

    def test_a_silent_network_writes_nothing(self):
        """TikTok answers nothing — that must not become a row of zeroes."""
        _delivery(platform="tiktok", external_id="tt1")
        self.assertEqual(collect_once(), 0)
        self.assertEqual(VideoMetric.objects.count(), 0)

    def test_threads_replies_are_stored_as_comments(self):
        """
        Threads calls them replies, the rest of our code calls them comments.
        The rename has to happen at the boundary or the digest reads zero.
        """
        from social.services import threads

        d = _delivery(platform="threads", external_id="th1")
        payload = {
            "data": [
                {"name": "views", "values": [{"value": 30}]},
                {"name": "replies", "values": [{"value": 2}]},
                {"name": "likes", "values": [{"value": 5}]},
            ]
        }
        with patch.object(threads, "_call", return_value=payload):
            collect_once()

        metric = VideoMetric.objects.get(delivery=d)
        self.assertEqual(metric.comments, 2)
        self.assertEqual(metric.views, 30)

    def test_instagram_views_come_from_insights(self):
        from social.services import meta

        d = _delivery(platform="instagram", external_id="ig1")
        payload = {
            "data": [
                {"name": "views", "values": [{"value": 99}]},
                {"name": "likes", "values": [{"value": 2}]},
                {"name": "comments", "values": [{"value": 0}]},
            ]
        }
        with patch.object(meta, "_graph", return_value=payload):
            collect_once()

        metric = VideoMetric.objects.get(delivery=d)
        self.assertEqual(metric.views, 99)
        self.assertEqual(metric.likes, 2)

    def test_instagram_falls_back_to_plain_fields_when_insights_refuses(self):
        """
        A revoked permission must cost us views, not the whole reading —
        otherwise it becomes a silent gap in the digest.
        """
        from social.services import meta

        d = _delivery(platform="instagram", external_id="ig1")

        def graph(method, path, **kwargs):
            if "insights" in path:
                raise meta.MetaPublishError("(#10) Application does not have permission")
            return {"like_count": 4, "comments_count": 1}

        with patch.object(meta, "_graph", side_effect=graph):
            collect_once()

        metric = VideoMetric.objects.get(delivery=d)
        self.assertIsNone(metric.views)
        self.assertEqual(metric.likes, 4)
        self.assertEqual(metric.comments, 1)

    def test_a_threads_metric_with_no_data_is_unknown_not_zero(self):
        """Insights omit a metric entirely rather than reporting it as zero."""
        from social.services import threads

        d = _delivery(platform="threads", external_id="th1")
        payload = {"data": [{"name": "likes", "values": [{"value": 4}]}]}
        with patch.object(threads, "_call", return_value=payload):
            collect_once()

        metric = VideoMetric.objects.get(delivery=d)
        self.assertIsNone(metric.views)
        self.assertEqual(metric.likes, 4)

    def test_one_failing_network_does_not_cost_the_others(self):
        _delivery(platform="youtube", external_id="yt1")
        ok = _delivery(platform="facebook", external_id="fb1")

        def flaky(delivery):
            if delivery.platform == "youtube":
                raise RuntimeError("boom")
            return {"views": 4, "likes": 1, "comments": 0}

        with patch.object(video_metrics, "fetch_for", side_effect=flaky):
            self.assertEqual(collect_once(), 1)

        self.assertEqual(VideoMetric.objects.get(delivery=ok).views, 4)

    def test_unknown_views_stay_none(self):
        """Instagram reports likes but not views. None, never 0."""
        d = _delivery(platform="instagram", external_id="ig1")
        with patch.object(
            video_metrics,
            "fetch_for",
            return_value={"views": None, "likes": 2, "comments": 0},
        ):
            collect_once()

        metric = VideoMetric.objects.get(delivery=d)
        self.assertIsNone(metric.views)
        self.assertEqual(metric.likes, 2)


class SummaryTests(TestCase):
    def _metric(self, delivery, day, views, likes=0, comments=0):
        return VideoMetric.objects.create(
            delivery=delivery,
            collected_on=day,
            views=views,
            likes=likes,
            comments=comments,
        )

    def test_only_the_latest_reading_counts(self):
        """
        Counters are cumulative. Summing daily snapshots would count the same
        view once per day it survived — a video with 10 views would report 70.
        """
        d = _delivery(platform="youtube")
        today = timezone.localtime().date()
        self._metric(d, today - timezone.timedelta(days=2), 4)
        self._metric(d, today - timezone.timedelta(days=1), 8)
        self._metric(d, today, 10)

        totals = weekly_summary()
        self.assertEqual(totals["youtube"]["views"], 10)
        self.assertEqual(totals["youtube"]["videos"], 1)

    def test_two_videos_on_one_network_add_up(self):
        today = timezone.localtime().date()
        self._metric(_delivery(external_id="a"), today, 3)
        self._metric(_delivery(external_id="b"), today, 7)

        totals = weekly_summary()
        self.assertEqual(totals["youtube"]["views"], 10)
        self.assertEqual(totals["youtube"]["videos"], 2)

    def test_a_network_without_views_is_not_reported_as_zero(self):
        """Any network may fail to report views — the fallback path can too."""
        d = _delivery(platform="instagram", external_id="ig1")
        self._metric(d, timezone.localtime().date(), None, likes=5)

        totals = weekly_summary()
        self.assertFalse(totals["instagram"]["views_known"])
        self.assertIn("перегляди н/д", format_summary(totals))
        self.assertNotIn("0 👁", format_summary(totals))

    def test_silent_networks_are_named_with_their_reason(self):
        """An empty line must read as a known limit, not a broken collector."""
        self._metric(_delivery(platform="youtube"), timezone.localtime().date(), 5)
        text = format_summary(weekly_summary())
        self.assertIn("threads_manage_insights", text)
        self.assertIn("video.list", text)

    def test_threads_stops_being_listed_as_silent_once_reauthorized(self):
        """
        The explanation has to disappear on its own. Left hard-coded, the
        report would keep asking for a permission already granted.
        """
        from social.models import ThreadsToken

        token = ThreadsToken.load()
        token.scope = "threads_basic,threads_manage_insights"
        token.save()

        self.assertNotIn(
            VideoDelivery.Platform.THREADS, video_metrics.silent_networks()
        )

    def test_threads_is_listed_as_silent_while_the_token_is_old(self):
        from social.models import ThreadsToken

        token = ThreadsToken.load()
        token.scope = "threads_basic,threads_content_publish"
        token.save()

        silent = video_metrics.silent_networks()
        self.assertIn("повторна авторизація", silent[VideoDelivery.Platform.THREADS])

    def test_best_network_is_listed_first(self):
        today = timezone.localtime().date()
        self._metric(_delivery(platform="youtube", external_id="y"), today, 2)
        self._metric(_delivery(platform="facebook", external_id="f"), today, 40)

        lines = format_summary(weekly_summary()).splitlines()
        network_lines = [line for line in lines if line.startswith("•")]
        self.assertIn("Facebook", network_lines[0])

    def test_digest_is_not_sent_when_there_is_nothing_to_say(self):
        with patch.object(video_metrics, "notify_staff_text", create=True) as notify:
            self.assertEqual(video_metrics.report_weekly(), "")
        notify.assert_not_called()


class ChartTests(TestCase):
    """
    Rendering itself is verified on the server: matplotlib 3.8.4 does not
    build on the Python running these tests locally. What is checked here is
    the part that decides whether we render at all.
    """

    def test_no_metrics_means_no_slide(self):
        """
        Returning an empty image would put a blank picture in the album. The
        report is better off with seven slides than eight with one lying.
        """
        from social.services.metrics_chart import build_social_photo

        self.assertIsNone(build_social_photo())

    def test_a_broken_chart_does_not_cost_the_album(self):
        from social.services import metrics_chart

        _delivery()
        VideoMetric.objects.create(
            delivery=VideoDelivery.objects.first(),
            collected_on=timezone.localtime().date(),
            views=5,
        )
        with patch.object(
            metrics_chart, "render_social_chart", side_effect=RuntimeError("no fonts")
        ):
            self.assertIsNone(metrics_chart.build_social_photo())


class SchedulerTests(TestCase):
    def test_metrics_are_collected_before_the_video_is_rendered(self):
        """
        Rendering is the slow, failure-prone step. A crash there must not cost
        the day its metrics.
        """
        import inspect

        from social.management.commands import tiktok_scheduler

        source = inspect.getsource(tiktok_scheduler._generate)
        self.assertLess(
            source.index("_collect_metrics"),
            source.index("build_final_video(pick)"),
        )
