"""Scheduled articles: published with a future published_at stay hidden until then."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from blog.models import Article


class ScheduledArticleTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.live = Article.objects.create(
            title="Як вибрати килим у вітальню",
            status=Article.Status.PUBLISHED,
            published_at=now - timedelta(days=1),
            description="<p>Живий текст.</p>",
        )
        self.future = Article.objects.create(
            title="Килим у дитячу: що знати",
            status=Article.Status.PUBLISHED,
            published_at=now + timedelta(days=2),
            description="<p>Майбутня стаття.</p>",
            meta_description="Майбутня стаття",
        )

    def test_queryset_public(self):
        public = list(Article.objects.public())
        self.assertIn(self.live, public)
        self.assertNotIn(self.future, public)
        # ...and it becomes public once its moment passes.
        later = timezone.now() + timedelta(days=3)
        self.assertIn(self.future, list(Article.objects.public(now=later)))

    def test_model_flags(self):
        self.assertTrue(self.live.is_public)
        self.assertFalse(self.live.is_scheduled)
        self.assertFalse(self.future.is_public)
        self.assertTrue(self.future.is_scheduled)
        self.assertTrue(self.future.is_public_at(timezone.now() + timedelta(days=3)))

    def test_publish_keeps_explicit_future_date(self):
        moment = timezone.now() + timedelta(days=5)
        article = Article.objects.create(title="Пізніше", published_at=moment)
        article.status = Article.Status.PUBLISHED
        article.save()
        article.refresh_from_db()
        self.assertEqual(article.published_at, moment)

    def test_first_publish_still_stamps_empty_date(self):
        article = Article.objects.create(title="Зараз", status=Article.Status.PUBLISHED)
        self.assertIsNotNone(article.published_at)
        self.assertTrue(article.is_public)

    def test_list_hides_scheduled(self):
        response = self.client.get(reverse("blog"))
        self.assertContains(response, self.live.title)
        self.assertNotContains(response, self.future.title)

    def test_detail_404_for_visitor(self):
        response = self.client.get(self.future.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_detail_visible_to_staff_as_noindex_preview(self):
        staff = get_user_model().objects.create_user(
            "editor@example.com", "pw", is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.get(self.future.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "noindex, nofollow")
        self.assertContains(response, "Стаття запланована на")
        # No Article rich result for a page that is not public yet.
        self.assertNotIn('"@type": "Article"', response.content.decode())

    def test_live_detail_has_article_jsonld(self):
        response = self.client.get(self.live.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn('"Article"', response.content.decode())
        self.assertNotContains(response, "Перегляд для персоналу")

    def test_sitemap_excludes_scheduled(self):
        from project.sitemaps import ArticleSitemap

        items = list(ArticleSitemap().items())
        self.assertIn(self.live, items)
        self.assertNotIn(self.future, items)

    def test_related_excludes_scheduled(self):
        from blog.views import related_articles

        self.assertNotIn(self.future, related_articles(self.live))

    def test_category_guides_exclude_scheduled(self):
        from project.seo_content import get_seo_guides

        guides = get_seo_guides(limit=10)
        self.assertIn(self.live, guides)
        self.assertNotIn(self.future, guides)

    def test_home_posts_exclude_scheduled_and_drafts(self):
        draft = Article.objects.create(title="Чернетка на головній")
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        posts = list(response.context["posts"])
        self.assertIn(self.live, posts)
        self.assertNotIn(self.future, posts)
        self.assertNotIn(draft, posts)

    def test_admin_visibility_column(self):
        from django.contrib.admin.sites import site

        admin = site._registry[Article]
        self.assertTrue(admin.visibility(self.future).startswith("Заплановано на "))
        self.assertEqual(admin.visibility(self.live), "Опубліковано")
        self.assertEqual(admin.visibility(Article(title="x")), "Чернетка")
        self.assertNotIn("published_at", admin.get_readonly_fields(None))
