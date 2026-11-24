"""Category page copy: shown on page 1 only; data migration never overwrites admin edits."""

import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from catalog.models import ProductCategory

mig = importlib.import_module("catalog.migrations.0049_fill_category_texts_2026_11")


class CategoryTextMigrationTests(TestCase):
    def test_fills_empty_fields_and_old_meta_only(self):
        c = ProductCategory.objects.create(
            title="Турецькі", slug="turetski", meta_title="Турецькі килими купити в Україні"
        )
        mine = ProductCategory.objects.create(
            title="Українські", slug="ukrayinski", intro="Свій текст", meta_title="Мій заголовок"
        )
        mig.forwards(django_apps, None)
        mig.forwards(django_apps, None)
        c.refresh_from_db(); mine.refresh_from_db()
        self.assertTrue(c.intro and c.body and len(c.faq) == 3)
        self.assertNotEqual(c.meta_title, "Турецькі килими купити в Україні")
        self.assertEqual(mine.intro, "Свій текст")
        self.assertEqual(mine.meta_title, "Мій заголовок")
        self.assertTrue(mine.body)
        for text in (c.intro, c.body, c.meta_title, c.meta_description):
            self.assertNotIn("—", text)
            self.assertNotIn("–", text)


class CategoryTextTemplateTests(TestCase):
    def setUp(self):
        self.cat = ProductCategory.objects.create(
            title="Турецькі", slug="turetski", intro="Вступ про турецькі",
            body="<p>Текст про турецькі килими</p>", faq=[{"q": "Питання тест?", "a": "Відповідь тест."}],
        )

    def test_page_one_shows_intro_body_and_faq(self):
        html = self.client.get(self.cat.get_absolute_url()).content.decode()
        self.assertIn("Вступ про турецькі", html)
        self.assertIn("Текст про турецькі килими", html)
        self.assertIn("Питання тест?", html)
