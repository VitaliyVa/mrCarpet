import json
from datetime import timedelta
from importlib import import_module

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.utils import timezone

from blog.models import Article
from social.models import SocialPost
from social.services.article_post import render_caption

migration = import_module("social.migrations.0030_plain_instagram_captions")


def historical_apps():
    loader = MigrationLoader(connection)
    return loader.project_state(("social", "0030_plain_instagram_captions")).apps


class PlainInstagramCaptionTests(TestCase):
    def setUp(self):
        SocialPost.objects.all().delete()
        self.data = json.loads(migration.DATA.read_text(encoding="utf-8"))
        self.slug = next(iter(self.data))
        self.article = Article.objects.filter(slug=self.slug).first() or Article.objects.create(
            title="Тест", slug=self.slug
        )
        link = "https://mrcarpet24.com/x"
        self.old = render_caption(self.data[self.slug]["old"], link, platform="instagram")
        self.new = render_caption(self.data[self.slug]["new"], link, platform="instagram")

    def make(self, status, caption):
        return SocialPost.objects.create(
            article=self.article, scheduled_at=timezone.now() + timedelta(days=2),
            status=status, caption="fb", caption_ig=caption, caption_fb="fb",
        )

    def test_matches_service_render_and_updates_once(self):
        self.assertEqual(migration.render(self.data[self.slug]["old"]), self.old)
        post = self.make("scheduled", self.old)
        migration.forwards(historical_apps(), None)
        migration.forwards(historical_apps(), None)
        post.refresh_from_db()
        self.assertEqual(post.caption_ig, self.new)

    def test_keeps_hand_edited_and_published(self):
        edited = self.make("scheduled", "Мій текст")
        published = self.make("published", self.old)
        migration.forwards(historical_apps(), None)
        edited.refresh_from_db(); published.refresh_from_db()
        self.assertEqual(edited.caption_ig, "Мій текст")
        self.assertEqual(published.caption_ig, self.old)

    def test_new_texts_plain_with_emoji(self):
        for slug, texts in self.data.items():
            new = texts["new"]
            self.assertNotIn("—", new, slug)
            self.assertFalse(new[0].isalnum(), slug)  # starts with an emoji
            self.assertIn("#", new, slug)
