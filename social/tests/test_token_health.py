"""
Tests: one daily answer to "is every credential still alive".

Four networks, four expiry models. A dead token never announces itself — the
run just stops posting somewhere and the loss shows up weeks later as "why
are there no Reels lately". These tests cover the cases that produce silence.
"""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from social.models import ThreadsToken, TikTokToken, YouTubeToken
from social.services import token_health
from social.services.token_health import check_all, format_report


def _tiktok(**kwargs):
    defaults = dict(
        access_token="a",
        refresh_token="r",
        refresh_expires_at=timezone.now() + timezone.timedelta(days=200),
    )
    defaults.update(kwargs)
    t = TikTokToken.load()
    for k, v in defaults.items():
        setattr(t, k, v)
    t.save()
    return t


def _threads(**kwargs):
    defaults = dict(
        access_token="a",
        user_id="u",
        expires_at=timezone.now() + timezone.timedelta(days=50),
    )
    defaults.update(kwargs)
    t = ThreadsToken.load()
    for k, v in defaults.items():
        setattr(t, k, v)
    t.save()
    return t


def _youtube(**kwargs):
    defaults = dict(access_token="a", refresh_token="r")
    defaults.update(kwargs)
    t = YouTubeToken.load()
    for k, v in defaults.items():
        setattr(t, k, v)
    t.save()
    return t


def _all_healthy():
    _tiktok()
    _threads()
    _youtube()


class HealthTests(TestCase):
    def setUp(self):
        # Meta has no expiry to read, so its check makes a call; stub it.
        self.meta = patch("social.services.meta._graph", return_value={"id": "1"})
        self.meta.start()
        self.addCleanup(self.meta.stop)
        self.configured = patch(
            "social.services.meta.meta_configured", return_value=True
        )
        self.configured.start()
        self.addCleanup(self.configured.stop)
        self.yt = patch(
            "social.services.youtube_auth.get_valid_access_token", return_value="tok"
        )
        self.yt.start()
        self.addCleanup(self.yt.stop)

    def test_all_four_networks_are_checked(self):
        _all_healthy()
        report = check_all()
        self.assertEqual(len(report.states), 4)
        self.assertTrue(report.healthy)

    def test_expired_threads_token_is_a_problem(self):
        _all_healthy()
        _threads(expires_at=timezone.now() - timezone.timedelta(days=1))
        report = check_all()
        threads = next(s for s in report.states if s.network == "Threads")
        self.assertFalse(threads.ok)
        self.assertTrue(threads.needs_human)

    def test_soon_to_expire_token_warns_before_it_breaks(self):
        """Fourteen days of notice beats an outage."""
        _all_healthy()
        _threads(expires_at=timezone.now() + timezone.timedelta(days=5))
        report = check_all()
        self.assertFalse(report.healthy)
        self.assertEqual(len(report.problems), 0)
        self.assertEqual(len(report.warnings), 1)

    def test_dead_meta_token_is_detected_by_using_it(self):
        """Page tokens carry no expiry, so the only honest check is a call."""
        _all_healthy()
        with patch("social.services.meta._graph", side_effect=RuntimeError("OAuth 190")):
            report = check_all()
        meta = next(s for s in report.states if s.network.startswith("Meta"))
        self.assertFalse(meta.ok)

    def test_youtube_invalid_grant_names_the_testing_trap(self):
        """
        The weekly death of a Testing-mode app reads like broken credentials.
        The report should say what it actually is.
        """
        _all_healthy()
        with patch(
            "social.services.youtube_auth.get_valid_access_token",
            side_effect=RuntimeError("invalid_grant"),
        ):
            report = check_all()
        yt = next(s for s in report.states if s.network == "YouTube")
        self.assertFalse(yt.ok)
        self.assertIn("Testing", yt.action)

    def test_unauthorized_networks_are_reported_not_crashed_on(self):
        report = check_all()
        self.assertEqual(len(report.states), 4)
        self.assertGreaterEqual(len(report.problems), 3)

    def test_one_broken_check_does_not_hide_the_others(self):
        _all_healthy()
        with patch.object(token_health, "_meta", side_effect=RuntimeError("boom")):
            report = check_all()
        self.assertEqual(len(report.states), 4)
        self.assertTrue(any("перевірка впала" in s.detail for s in report.states))


class ReportTests(TestCase):
    def setUp(self):
        patcher = patch("social.services.meta.meta_configured", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        graph = patch("social.services.meta._graph", return_value={"id": "1"})
        graph.start()
        self.addCleanup(graph.stop)
        yt = patch(
            "social.services.youtube_auth.get_valid_access_token", return_value="tok"
        )
        yt.start()
        self.addCleanup(yt.stop)

    def test_healthy_report_stays_quiet(self):
        """
        A daily "all fine" trains people to ignore the channel, and this
        message has to be worth reading the one time it is not fine.
        """
        _all_healthy()
        with patch("social.services.comment_notify.notify_staff_text") as notify:
            token_health.run_and_report()
        notify.assert_not_called()

    def test_problem_report_is_sent_to_the_video_topic(self):
        _all_healthy()
        _threads(expires_at=timezone.now() - timezone.timedelta(days=1))
        with patch("social.services.comment_notify.notify_staff_text") as notify:
            token_health.run_and_report()
        self.assertTrue(notify.called)
        self.assertTrue(notify.call_args.kwargs["video"])

    def test_report_names_the_action_needed(self):
        _all_healthy()
        _threads(expires_at=timezone.now() - timezone.timedelta(days=1))
        text = format_report(check_all())
        self.assertIn("Threads", text)
        self.assertIn("OAuth", text)
        self.assertIn("потрібні руки", text)

    def test_always_flag_forces_a_message(self):
        _all_healthy()
        with patch("social.services.comment_notify.notify_staff_text") as notify:
            token_health.run_and_report(always=True)
        self.assertTrue(notify.called)
