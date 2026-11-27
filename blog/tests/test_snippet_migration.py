from importlib import import_module

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from blog.models import Article

migration = import_module("blog.migrations.0013_clearer_snippets_low_ctr_articles")


def historical_apps():
    return MigrationLoader(connection).project_state(
        ("blog", "0013_clearer_snippets_low_ctr_articles")
    ).apps


class ClearerSnippetsTests(TestCase):
    slug = "polipropilen-poliester-i-dzhutova-osnova-porivniannia-kilimiv"

    def article(self, **kw):
        Article.objects.filter(slug=self.slug).delete()
        return Article.objects.create(title="Тест", slug=self.slug, **kw)

    def test_updates_old_values_once(self):
        c = migration.CHANGES[self.slug]
        a = self.article(meta_title=c["old_title"], meta_description=c["old_description"])
        migration.forwards(historical_apps(), None)
        migration.forwards(historical_apps(), None)
        a.refresh_from_db()
        self.assertEqual(a.meta_title, c["title"])
        self.assertEqual(a.meta_description, c["description"])

    def test_keeps_admin_edits(self):
        a = self.article(meta_title="Свій заголовок", meta_description="Свій опис")
        migration.forwards(historical_apps(), None)
        a.refresh_from_db()
        self.assertEqual(a.meta_title, "Свій заголовок")
        self.assertEqual(a.meta_description, "Свій опис")

    def test_texts_plain(self):
        for c in migration.CHANGES.values():
            for key in ("title", "description"):
                if c[key]:
                    self.assertNotIn("—", c[key])
                    self.assertFalse(c[key].startswith("Дізнайтеся"))
            self.assertLessEqual(len(c["description"]), 160)
