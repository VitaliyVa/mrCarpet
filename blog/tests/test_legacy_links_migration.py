"""blog 0011 adds product cards to the 7 original articles, once."""

import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from blog.models import Article

mig = importlib.import_module("blog.migrations.0011_link_legacy_articles_to_products")

SLUG = "kilimok-u-vannu-iak-vibrati-shchob-ne-kovzav-i-shvidko-sokh"
BODY = "<p>Вступ</p><h2>Один</h2><p>a</p><h2>Два</h2><p>b</p><h2>Три</h2><p>c</p><h2>Читайте також</h2>"


class LegacyArticleLinksTests(TestCase):
    def setUp(self):
        self.art = Article.objects.create(slug=SLUG, title="Килимок у ванну", description=BODY, status="published")

    def test_block_goes_before_the_third_heading_and_only_once(self):
        mig.forwards(django_apps, None)
        mig.forwards(django_apps, None)
        d = Article.objects.get(pk=self.art.pk).description
        self.assertEqual(d.count("blog-products"), 1)
        self.assertIn('href="/catalog/categorie/dlia-vanni/"', d)
        self.assertLess(d.index("blog-products"), d.index("<h2>Три</h2>"))
        self.assertGreater(d.index("blog-products"), d.index("<h2>Два</h2>"))
        self.assertNotIn("—", d)

    def test_existing_cards_are_left_alone(self):
        Article.objects.filter(pk=self.art.pk).update(description=BODY + '<div class="blog-products" data-products="x"></div>')
        mig.forwards(django_apps, None)
        self.assertEqual(Article.objects.get(pk=self.art.pk).description.count("blog-products"), 1)

    def test_short_article_gets_block_at_the_end(self):
        self.assertTrue(mig.insert_block("<p>x</p>", "<div>B</div>").endswith("<div>B</div>"))
