import json
from datetime import timedelta
from importlib import import_module

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone

from blog.models import Article
from social.models import SocialPost
from social.services.article_post import render_caption
from social.services.media_urls import article_campaign, article_share_url

migration = import_module("social.migrations.0027_rewrite_dry_facebook_captions")


class FacebookCaptionRewriteTests(TestCase):
    def setUp(self):
        SocialPost.objects.all().delete()
        self.rewrites = json.loads(migration.DATA.read_text(encoding="utf-8"))
        self.slug = next(iter(self.rewrites))
        self.article = Article.objects.filter(slug=self.slug).first() or Article.objects.create(
            title="Тест", slug=self.slug
        )
        campaign = article_campaign(self.article)
        self.link = article_share_url(self.article, "facebook", campaign)
        self.old = render_caption(self.rewrites[self.slug]["old"], self.link, platform="facebook")
        self.new = render_caption(self.rewrites[self.slug]["new"], self.link, platform="facebook")

    def make(self, status, caption):
        return SocialPost.objects.create(
            article=self.article, scheduled_at=timezone.now() + timedelta(days=3),
            status=status, caption=caption, caption_fb=caption,
            utm_campaign=article_campaign(self.article),
        )

    def test_rewrites_untouched_scheduled_post_once(self):
        post = self.make("scheduled", self.old)
        migration.forwards(django_apps, None)
        migration.forwards(django_apps, None)
        post.refresh_from_db()
        self.assertEqual(post.caption_fb, self.new)
        self.assertEqual(post.caption, self.new)
        self.assertIn(self.link, post.caption_fb)
        self.assertNotIn("—", post.caption_fb)

    def test_keeps_hand_edited_and_published(self):
        edited = self.make("scheduled", "Свій текст власника")
        published = self.make("published", self.old)
        migration.forwards(django_apps, None)
        edited.refresh_from_db(); published.refresh_from_db()
        self.assertEqual(edited.caption_fb, "Свій текст власника")
        self.assertEqual(published.caption_fb, self.old)

    def test_new_texts_are_multiline_without_long_dashes(self):
        for slug, texts in self.rewrites.items():
            body = texts["new"].split("{link}")[0]
            self.assertGreater(len([l for l in body.splitlines() if l.strip()]), 1, slug)
            self.assertNotIn("—", texts["new"], slug)
            self.assertNotIn("–", texts["new"], slug)
