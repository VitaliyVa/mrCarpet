"""Scheduled article announcements: UTM links, slides, spec → post, release."""

import io
import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from blog.models import Article
from social.models import SocialPost, SocialPostImage

LONG_UA = (
    "Ґанок, їжачок і є’ятий апостроф: дуже довгий український текст без жодного "
    "сенсу, який має перенестися по словах, зменшитися і ніколи не вилізти за "
    "межі слайда. " * 12
)


def _png_bytes(size=(1600, 1000), color=(120, 90, 60)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


class MediaTestCase(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="mc-media-")
        self._override = override_settings(MEDIA_ROOT=self.media)
        self._override.enable()
        (Path(self.media) / "articles").mkdir()
        (Path(self.media) / "articles" / "cover.png").write_bytes(_png_bytes())

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def make_article(self, **kw):
        defaults = dict(
            title="Килимок під двері: гумовий чи ворсовий",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now() - timedelta(hours=1),
            image="articles/cover.png",
            description="<p>Текст</p>",
        )
        defaults.update(kw)
        return Article.objects.create(**defaults)


class ArticleShareUrlTests(TestCase):
    def test_utm_per_platform(self):
        from social.services.media_urls import article_share_url

        article = Article.objects.create(title="Як чистити килим", slug="yak-chystyty")
        url = article_share_url(article, "instagram", "blog-yak-chystyty")
        self.assertEqual(
            url,
            "https://mrcarpet24.com/blog/article/yak-chystyty/"
            "?utm_source=instagram&utm_medium=social&utm_campaign=blog-yak-chystyty",
        )
        self.assertIn("utm_source=facebook", article_share_url(article, "facebook", "x"))
        self.assertIn("utm_source=tiktok", article_share_url(article, "tt", "x"))
        # Campaign defaults to blog-<slug>.
        self.assertIn("utm_campaign=blog-yak-chystyty", article_share_url(article, "fb"))

    def test_build_caption_uses_article_link(self):
        from social.services.media_urls import build_caption

        article = Article.objects.create(title="Стаття", slug="stattia")
        post = SocialPost.objects.create(
            media_kind=SocialPost.MediaKind.PHOTOS, article=article, caption="Привіт"
        )
        cap = build_caption(post, "facebook")
        self.assertIn("/blog/article/stattia/?utm_source=facebook", cap)
        self.assertIn("utm_campaign=blog-stattia", cap)
        self.assertNotIn("/catalog/", cap)

    def test_product_posts_unchanged(self):
        from social.services.media_urls import build_caption

        post = SocialPost.objects.create(caption="Привіт")
        self.assertIn("/catalog/?utm_source=social", build_caption(post, "instagram"))


class SocialCardsTests(MediaTestCase):
    def test_fit_text_never_overflows(self):
        from blog.services.social_cards import fit_text

        fitted = fit_text(LONG_UA, "book", 900, 400, max_size=50, min_size=30)
        self.assertLessEqual(fitted.height, 400)
        for line in fitted.lines:
            self.assertLessEqual(fitted.font.getlength(line), 900)
        self.assertTrue(fitted.lines[-1].endswith("…"))

    def test_long_single_word_is_split(self):
        from blog.services.social_cards import fit_text

        fitted = fit_text("Ж" * 200, "bold", 300, 2000, max_size=60, min_size=40)
        for line in fitted.lines:
            self.assertLessEqual(fitted.font.getlength(line), 300)

    def test_slides_sizes_and_count(self):
        from blog.services.social_cards import CardSpec, render_article_slides

        article = self.make_article()
        spec = CardSpec(
            hook=LONG_UA,
            tips=[{"title": LONG_UA, "text": LONG_UA}, {"title": "Коротко", "text": "Так."}],
        )
        slides = render_article_slides(article, spec)
        self.assertEqual(len(slides), 3)  # no products → no product slide
        for img in slides:
            self.assertEqual(img.size, (1080, 1350))

    def test_slides_without_cover(self):
        from blog.services.social_cards import CardSpec, render_article_slides

        article = self.make_article(image=None)
        slides = render_article_slides(article, CardSpec(hook="Гачок", tips=[]))
        self.assertEqual([s.size for s in slides], [(1080, 1350)])

    def test_product_slide_renders(self):
        from blog.services.social_cards import ProductTile, render_products

        tiles = [
            ProductTile(title=LONG_UA, price_line="від 2 300 грн",
                        image=Image.new("RGB", (400, 600), (200, 180, 160))),
            ProductTile(title="Килим", price_line="900 грн"),
        ]
        img = render_products(4, 4, tiles)
        self.assertEqual(img.size, (1080, 1350))


SPEC = {
    "hook": "Гумовий чи ворсовий килимок під двері?",
    "tips": [
        {"title": "Гума не ковзає", "text": "Лежить рівно навіть на плитці."},
        {"title": "Ворс тримає пісок", "text": "Бруд не йде далі в дім."},
    ],
    "caption_ig": "Порівняли два килимки.",
    "caption_fb": "Порівняли два килимки. Читайте: {link}",
    "products": [],
}


class SchedulePostTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        # The 2026-11 data migration schedules real article posts in the test
        # DB too; these tests count posts, so start from an empty table.
        SocialPost.objects.all().delete()

    def test_creates_scheduled_photo_post(self):
        from social.services.article_post import schedule_article_post

        article = self.make_article(slug="kylymok")
        post = schedule_article_post("kylymok", SPEC, "2026-12-01 18:00")

        self.assertEqual(post.status, SocialPost.Status.SCHEDULED)
        self.assertEqual(post.media_kind, SocialPost.MediaKind.PHOTOS)
        self.assertEqual(post.article, article)
        self.assertTrue(post.target_instagram and post.target_facebook)
        self.assertFalse(post.target_tiktok)
        self.assertEqual(post.utm_campaign, "blog-kylymok")
        # 18:00 Kyiv in December = 16:00 UTC.
        self.assertEqual(post.scheduled_at.astimezone(timezone.utc).hour, 16)
        self.assertEqual(post.images.count(), 3)
        first = post.ordered_images().first()
        self.assertTrue(first.image.name.startswith("social/article_cards/kylymok/"))
        self.assertTrue((Path(self.media) / first.image.name).exists())
        self.assertIn("utm_source=facebook", post.caption_fb)
        self.assertNotIn("{link}", post.caption_fb)
        self.assertTrue(post.caption_ig.endswith("Повна стаття за посиланням у профілі"))

    def test_idempotent_same_time(self):
        from social.services.article_post import schedule_article_post

        self.make_article(slug="kylymok")
        first = schedule_article_post("kylymok", SPEC, "2026-12-01 18:00")
        spec = dict(SPEC, caption_ig="Нова версія.")
        second = schedule_article_post("kylymok", spec, "2026-12-01 18:00")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SocialPost.objects.count(), 1)
        self.assertEqual(SocialPostImage.objects.count(), 3)
        self.assertIn("Нова версія.", second.caption_ig)

    def test_published_post_is_not_touched(self):
        from social.services.article_post import schedule_article_post

        self.make_article(slug="kylymok")
        post = schedule_article_post("kylymok", SPEC, "2026-12-01 18:00")
        SocialPost.objects.filter(pk=post.pk).update(status=SocialPost.Status.PUBLISHED)
        again = schedule_article_post("kylymok", dict(SPEC, caption_ig="Інше"), "2026-12-01 18:00")
        self.assertEqual(again.status, SocialPost.Status.PUBLISHED)
        self.assertNotIn("Інше", again.caption_ig)

    def test_too_many_tips(self):
        from social.services.article_post import SpecError, schedule_article_post

        self.make_article(slug="kylymok")
        spec = dict(SPEC, tips=[{"title": "x", "text": "y"}] * 5)
        with self.assertRaises(SpecError):
            schedule_article_post("kylymok", spec, "2026-12-01 18:00")

    def test_command_dry_run_writes_files_only(self):
        self.make_article(slug="kylymok")
        spec_path = Path(self.media) / "spec.json"
        spec_path.write_text(json.dumps(SPEC, ensure_ascii=False), encoding="utf-8")
        out = Path(self.media) / "preview"
        stdout = io.StringIO()
        call_command(
            "create_article_social_post", "kylymok",
            spec=str(spec_path), dry_run=True, out=str(out), stdout=stdout,
        )
        files = sorted(p.name for p in out.iterdir())
        self.assertEqual(files, ["01.jpg", "02.jpg", "03.jpg"])
        with Image.open(out / "01.jpg") as img:
            self.assertEqual(img.size, (1080, 1350))
        self.assertEqual(SocialPost.objects.count(), 0)

    def test_command_schedules(self):
        self.make_article(slug="kylymok")
        spec_path = Path(self.media) / "spec.json"
        spec_path.write_text(json.dumps(SPEC, ensure_ascii=False), encoding="utf-8")
        call_command(
            "create_article_social_post", "kylymok",
            spec=str(spec_path), at="2026-12-01 18:00", stdout=io.StringIO(),
        )
        self.assertEqual(
            SocialPost.objects.get().status, SocialPost.Status.SCHEDULED
        )


class ReleaseDuePostsTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        # data migrations seed real scheduled posts; once their time passes they are due
        SocialPost.objects.all().delete()

    def _post(self, article=None, at=None, status=SocialPost.Status.SCHEDULED):
        return SocialPost.objects.create(
            media_kind=SocialPost.MediaKind.PHOTOS,
            article=article,
            scheduled_at=at or timezone.now() - timedelta(minutes=1),
            status=status,
        )

    def _fake_publish(self, post_id):
        SocialPost.objects.filter(pk=post_id).update(status=SocialPost.Status.PUBLISHED)
        return SocialPost.objects.get(pk=post_id)

    def test_publishes_due_exactly_once(self):
        from social.services.scheduled import release_due_posts

        post = self._post(article=self.make_article())
        with mock.patch(
            "social.services.publish.publish_post", side_effect=self._fake_publish
        ) as pub:
            release_due_posts()
            release_due_posts()
        pub.assert_called_once_with(post.pk)
        post.refresh_from_db()
        self.assertEqual(post.status, SocialPost.Status.PUBLISHED)

    def test_claim_guard_loses_race(self):
        """Another worker claimed the row between the select and our update."""
        from social.services import scheduled

        post = self._post()
        real_claim = scheduled._claim

        def racing_claim(post_id, now):
            real_claim(post_id, now)  # the other worker wins
            return real_claim(post_id, now)  # ours finds nothing to claim

        with mock.patch.object(scheduled, "_claim", side_effect=racing_claim), \
                mock.patch("social.services.publish.publish_post") as pub:
            scheduled.release_due_posts()
        pub.assert_not_called()
        post.refresh_from_db()
        self.assertEqual(post.status, SocialPost.Status.PUBLISHING)

    def test_future_posts_wait(self):
        from social.services.scheduled import release_due_posts

        self._post(at=timezone.now() + timedelta(hours=1))
        with mock.patch("social.services.publish.publish_post") as pub:
            release_due_posts()
        pub.assert_not_called()

    def test_skips_until_article_is_public(self):
        from social.services.scheduled import release_due_posts

        article = self.make_article(published_at=timezone.now() + timedelta(hours=2))
        post = self._post(article=article)
        draft_post = self._post(article=self.make_article(title="Чернетка", status=Article.Status.DRAFT, published_at=None))
        with mock.patch(
            "social.services.publish.publish_post", side_effect=self._fake_publish
        ) as pub:
            lines = release_due_posts()
            pub.assert_not_called()
            self.assertTrue(any("waits for article" in line for line in lines))
            post.refresh_from_db()
            self.assertEqual(post.status, SocialPost.Status.SCHEDULED)

            # Once the article's moment has passed, the post goes out.
            release_due_posts(now=timezone.now() + timedelta(hours=3))
        pub.assert_called_once_with(post.pk)
        draft_post.refresh_from_db()
        self.assertEqual(draft_post.status, SocialPost.Status.SCHEDULED)

    def test_ignores_other_statuses(self):
        from social.services.scheduled import release_due_posts

        self._post(status=SocialPost.Status.DRAFT)
        self._post(status=SocialPost.Status.QUEUED)
        with mock.patch("social.services.publish.publish_post") as pub:
            release_due_posts()
        pub.assert_not_called()

    def test_crash_marks_failed_without_retry(self):
        from social.services.scheduled import release_due_posts

        post = self._post()
        with mock.patch(
            "social.services.publish.publish_post", side_effect=RuntimeError("boom")
        ) as pub:
            release_due_posts()
            release_due_posts()
        self.assertEqual(pub.call_count, 1)
        post.refresh_from_db()
        self.assertEqual(post.status, SocialPost.Status.FAILED)
        self.assertIn("boom", post.last_error)

    def test_scheduler_tick_survives_release_errors(self):
        from social.management.commands import tiktok_scheduler

        with mock.patch.object(tiktok_scheduler, "_publish_due", return_value=""), \
                mock.patch(
                    "social.services.scheduled.release_due_posts",
                    side_effect=RuntimeError("db down"),
                ):
            out = tiktok_scheduler._tick()
        self.assertIn("scheduled posts failed", out)

    def test_scheduler_tick_releases(self):
        from social.management.commands import tiktok_scheduler

        post = self._post()
        with mock.patch.object(tiktok_scheduler, "_publish_due", return_value=""), \
                mock.patch(
                    "social.services.publish.publish_post", side_effect=self._fake_publish
                ):
            out = tiktok_scheduler._tick()
        self.assertIn(f"post #{post.pk}", out)

    def test_content_scheduler_once(self):
        from social.management.commands import content_scheduler

        post = self._post()
        with mock.patch(
            "social.services.publish.publish_post", side_effect=self._fake_publish
        ) as pub:
            out = io.StringIO()
            call_command("content_scheduler", once=True, stdout=out)
            call_command("content_scheduler", once=True, stdout=io.StringIO())
        pub.assert_called_once_with(post.pk)
        self.assertIn(f"post #{post.pk}", out.getvalue())

        with mock.patch(
            "social.services.scheduled.release_due_posts", side_effect=RuntimeError("x")
        ):
            self.assertIn("release failed", content_scheduler.run_once())

    def test_content_scheduler_tick_alignment(self):
        from datetime import datetime

        from social.management.commands.content_scheduler import KYIV, next_tick

        self.assertEqual(
            next_tick(datetime(2026, 12, 1, 17, 57, 30, tzinfo=KYIV)),
            datetime(2026, 12, 1, 18, 0, tzinfo=KYIV),
        )
        self.assertEqual(
            next_tick(datetime(2026, 12, 1, 18, 0, 0, tzinfo=KYIV)),
            datetime(2026, 12, 1, 18, 5, tzinfo=KYIV),
        )

    def test_admin_schedule_actions(self):
        from django.contrib.admin.sites import site
        from django.contrib.auth import get_user_model
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        admin = site._registry[SocialPost]
        user = get_user_model().objects.create_superuser("r@example.com", "pw")
        request = RequestFactory().post("/")
        request.user = user
        request.session = {}
        request._messages = FallbackStorage(request)

        post = SocialPost.objects.create(
            media_kind=SocialPost.MediaKind.PHOTOS,
            scheduled_at=timezone.now() + timedelta(days=1),
        )
        SocialPostImage.objects.create(post=post, image="articles/cover.png")
        admin.action_schedule(request, SocialPost.objects.filter(pk=post.pk))
        post.refresh_from_db()
        self.assertEqual(post.status, SocialPost.Status.SCHEDULED)
        self.assertTrue(admin.schedule_label(post).startswith("Заплановано на "))

        admin.action_unschedule(request, SocialPost.objects.filter(pk=post.pk))
        post.refresh_from_db()
        self.assertEqual(post.status, SocialPost.Status.DRAFT)
