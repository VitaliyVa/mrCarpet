"""
Tests: inbound YouTube comments → staff video topic.

YouTube has no webhooks for comments, so this is the one network we have to
ask. The parts that carry risk: not alerting on our own replies, not
re-alerting every hour, and surviving a video with comments turned off.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from social.models import (
    SocialCommentReply,
    TikTokDailyPick,
    VideoDelivery,
    YouTubeToken,
)
from social.services import youtube_comments
from social.services.youtube_comments import fetch_comments, poll_once, recent_video_ids

KEY = dict(YOUTUBE_API_KEY="AIza-test-key")
OWN_CHANNEL = "UCYssNNgxKFKEPSXRo8SDoLg"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"x"

    def json(self):
        return self._payload


def _thread(comment_id="c1", text="2000?", author="buyer", channel="UCbuyer"):
    return {
        "snippet": {
            "topLevelComment": {
                "id": comment_id,
                "snippet": {
                    "textOriginal": text,
                    "authorDisplayName": author,
                    "authorChannelId": {"value": channel},
                    "publishedAt": "2026-07-21T12:00:00Z",
                },
            }
        }
    }


def _delivery(external_id="vid1", days_ago=0):
    pick = TikTokDailyPick.objects.create()
    return VideoDelivery.objects.create(
        pick=pick,
        platform=VideoDelivery.Platform.YOUTUBE,
        status=VideoDelivery.Status.PUBLISHED,
        external_id=external_id,
        published_at=timezone.now() - timezone.timedelta(days=days_ago),
    )


@override_settings(**KEY)
class FetchTests(TestCase):
    def setUp(self):
        token = YouTubeToken.load()
        token.channel_id = OWN_CHANNEL
        token.save()

    def test_comment_is_parsed(self):
        payload = {"items": [_thread()]}
        with patch.object(youtube_comments.requests, "get", return_value=FakeResponse(payload)):
            comments = fetch_comments("vid1")

        self.assertEqual(len(comments), 1)
        c = comments[0]
        self.assertEqual(c.platform, "youtube")
        self.assertEqual(c.text, "2000?")
        self.assertEqual(c.external_id, "c1")
        self.assertEqual(c.parent_post_id, "vid1")
        self.assertIn("shorts/vid1", c.post_url)

    def test_our_own_comment_is_ignored(self):
        """A reply from the channel must not return as a fresh question."""
        payload = {"items": [_thread(channel=OWN_CHANNEL)]}
        with patch.object(youtube_comments.requests, "get", return_value=FakeResponse(payload)):
            self.assertEqual(fetch_comments("vid1"), [])

    def test_empty_text_is_skipped(self):
        payload = {"items": [_thread(text="   ")]}
        with patch.object(youtube_comments.requests, "get", return_value=FakeResponse(payload)):
            self.assertEqual(fetch_comments("vid1"), [])

    def test_disabled_comments_are_not_an_error(self):
        payload = {"error": {"errors": [{"reason": "commentsDisabled"}]}}
        with patch.object(
            youtube_comments.requests, "get", return_value=FakeResponse(payload, 403)
        ):
            self.assertEqual(fetch_comments("vid1"), [])

    def test_http_failure_is_swallowed(self):
        with patch.object(
            youtube_comments.requests,
            "get",
            side_effect=youtube_comments.requests.RequestException("boom"),
        ):
            self.assertEqual(fetch_comments("vid1"), [])

    def test_no_api_key_means_no_calls(self):
        with override_settings(YOUTUBE_API_KEY=""):
            with patch.object(youtube_comments.requests, "get") as get:
                self.assertEqual(fetch_comments("vid1"), [])
            get.assert_not_called()

    def test_the_upload_token_is_not_used(self):
        """
        Reading comments needs youtube.readonly, which the grant deliberately
        lacks — a key keeps the uploader's token untouched.
        """
        payload = {"items": []}
        with patch.object(
            youtube_comments.requests, "get", return_value=FakeResponse(payload)
        ) as get:
            fetch_comments("vid1")
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["key"], "AIza-test-key")
        self.assertNotIn("Authorization", get.call_args.kwargs.get("headers", {}))


@override_settings(**KEY)
class PollTests(TestCase):
    def setUp(self):
        token = YouTubeToken.load()
        token.channel_id = OWN_CHANNEL
        token.save()

    def test_only_recent_videos_are_polled(self):
        """Interest in a Short dies fast; polling the whole history would grow."""
        _delivery("fresh", days_ago=1)
        _delivery("stale", days_ago=30)
        ids = recent_video_ids()
        self.assertIn("fresh", ids)
        self.assertNotIn("stale", ids)

    def test_new_comment_reaches_the_video_topic(self):
        _delivery("vid1")
        payload = {"items": [_thread()]}
        with patch.object(youtube_comments.requests, "get", return_value=FakeResponse(payload)), \
             patch.object(youtube_comments, "staff_comments_configured", return_value=True), \
             patch.object(youtube_comments, "notify_staff_comment",
                          return_value={"ok": True}) as notify:
            sent = poll_once()

        self.assertEqual(sent, 1)
        self.assertTrue(notify.call_args.kwargs["video"])

    def test_seen_comment_is_not_alerted_again(self):
        """Without this the same comment would arrive every hour, forever."""
        _delivery("vid1")
        SocialCommentReply.objects.create(
            platform="youtube",
            external_comment_id="c1",
            comment_text="2000?",
            alert_chat_id="-100500",
            alert_message_id="1",
        )
        payload = {"items": [_thread()]}
        with patch.object(youtube_comments.requests, "get", return_value=FakeResponse(payload)), \
             patch.object(youtube_comments, "staff_comments_configured", return_value=True), \
             patch.object(youtube_comments, "notify_staff_comment") as notify:
            self.assertEqual(poll_once(), 0)
        notify.assert_not_called()

    def test_no_videos_means_no_calls(self):
        with patch.object(youtube_comments.requests, "get") as get, \
             patch.object(youtube_comments, "staff_comments_configured", return_value=True):
            self.assertEqual(poll_once(), 0)
        get.assert_not_called()

    def test_missing_key_short_circuits(self):
        _delivery("vid1")
        with override_settings(YOUTUBE_API_KEY=""):
            with patch.object(youtube_comments.requests, "get") as get:
                self.assertEqual(poll_once(), 0)
            get.assert_not_called()


class SchedulerTests(TestCase):
    """The poll shares the loop with the two daily slots."""

    def test_tick_is_scheduled_every_ten_minutes(self):
        """
        The stagger releases a network every 20 minutes, so the loop has to
        wake at least that often to let them out.
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from social.management.commands.tiktok_scheduler import next_run

        now = datetime(2026, 7, 21, 9, 15, tzinfo=ZoneInfo("Europe/Kyiv"))
        moment, action = next_run(now)
        self.assertEqual(action, "tick")
        self.assertEqual((moment.hour, moment.minute), (9, 20))

    def test_daily_slots_still_win_when_closer(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from social.management.commands.tiktok_scheduler import next_run

        # 03:10 → generate at 04:00 lands before the 04:00 poll would matter.
        now = datetime(2026, 7, 21, 3, 55, tzinfo=ZoneInfo("Europe/Kyiv"))
        moment, action = next_run(now)
        self.assertEqual((moment.hour, moment.minute), (4, 0))
        self.assertEqual(action, "generate")
