"""Catalog structure on product and category pages.

* the main (primary) category of a product: room/purpose over country;
* product breadcrumbs: Головна > Каталог > категорія > товар (HTML = JSON-LD);
* «Схожі товари» filled automatically when none were picked by hand;
* «Корисні статті» on a category page: articles about that category first;
* «Перейти в каталог» under an article leads to the category it is about.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone


def _ld_nodes(html, type_):
    out = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(raw)
        for node in data if isinstance(data, list) else [data]:
            if node.get("@type") == type_:
                out.append(node)
    return out


class _CatalogFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        from catalog.models import Product, ProductAttribute, ProductCategory, Size

        # Country categories get the lowest pks, as on the live site, so the
        # old `categories.first()` picked them.
        cls.turkish = ProductCategory.objects.create(title="Турецькі", slug="turetski")
        cls.ukrainian = ProductCategory.objects.create(title="Українські", slug="ukrayinski")
        cls.bath = ProductCategory.objects.create(title="Для ванни", slug="dlia-vanni")
        cls.door = ProductCategory.objects.create(title="Під двері", slug="pid-dveri")
        cls.size = Size.objects.create(title="0.6x1.0")

        def make(title, slug, cats, quantity=3):
            p = Product.objects.create(title=title, slug=slug)
            ProductAttribute.objects.create(
                product=p, size=cls.size, price=450, quantity=quantity
            )
            p.categories.add(*cats)
            return p

        cls.make = staticmethod(make)
        cls.isadora = make(
            "Килим фіолетово-ліловий для ванни isadora",
            "kilim-isadora-t",
            [cls.turkish, cls.bath],
        )
        cls.bath_others = [
            make(f"Килим для ванни модель{i}", f"kilim-vanna-{i}-t", [cls.turkish, cls.bath])
            for i in range(10)
        ]
        cls.bath_sold_out = make(
            "Килим для ванни розпродано", "kilim-vanna-sold-t", [cls.bath], quantity=0
        )
        cls.country_only = make("Килим Prime 123", "kilim-prime-t", [cls.ukrainian])
        cls.door_mat = make("Килим Під двері сірий", "kilim-dveri-t", [cls.ukrainian, cls.door])


class PrimaryCategoryTests(_CatalogFixture):
    def test_room_beats_country(self):
        from catalog.utils import primary_category

        self.assertEqual(primary_category(self.isadora), self.bath)
        self.assertEqual(primary_category(self.door_mat), self.door)

    def test_country_when_no_room(self):
        from catalog.models import Product
        from catalog.utils import primary_category

        self.assertEqual(primary_category(self.country_only), self.ukrainian)
        bare = Product.objects.create(title="Без категорії", slug="bez-kat-t")
        self.assertIsNone(primary_category(bare))


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL="https://mrcarpet24.com")
class ProductBreadcrumbTests(_CatalogFixture):
    def test_breadcrumb_html_and_jsonld_use_room_category(self):
        response = self.client.get(self.isadora.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        crumbs_html = html.split('class="bread-crumbs"')[1].split("</div>")[0]
        self.assertIn('href="/catalog/"', crumbs_html)
        self.assertIn(">Каталог<", crumbs_html)
        self.assertIn('href="/catalog/categorie/dlia-vanni/"', crumbs_html)
        self.assertNotIn("turetski", crumbs_html)

        (crumbs,) = _ld_nodes(html, "BreadcrumbList")
        names = [e["name"] for e in crumbs["itemListElement"]]
        self.assertEqual(names, ["Головна", "Каталог", "Для ванни", self.isadora.title])
        self.assertEqual(
            crumbs["itemListElement"][2]["item"],
            "https://mrcarpet24.com/catalog/categorie/dlia-vanni/",
        )

    def test_breadcrumb_without_category(self):
        from catalog.models import Product, ProductAttribute

        bare = Product.objects.create(title="Килим без категорії", slug="bez-kat-crumb-t")
        ProductAttribute.objects.create(product=bare, size=self.size, price=100, quantity=1)
        html = self.client.get(bare.get_absolute_url()).content.decode()
        (crumbs,) = _ld_nodes(html, "BreadcrumbList")
        names = [e["name"] for e in crumbs["itemListElement"]]
        self.assertEqual(names, ["Головна", "Каталог", bare.title])

    def test_view_item_keeps_country_and_adds_room(self):
        response = self.client.get(self.isadora.get_absolute_url())
        payload = response.context["analytics_view_item"]
        self.assertEqual(payload["item_category"], "Турецькі")
        self.assertEqual(payload["item_category2"], "Для ванни")

        response = self.client.get(self.country_only.get_absolute_url())
        payload = response.context["analytics_view_item"]
        self.assertEqual(payload["item_category"], "Українські")
        self.assertNotIn("item_category2", payload)


class RelatedProductsTests(_CatalogFixture):
    def _related(self, product):
        return self.client.get(product.get_absolute_url()).context["related_products"]

    def test_auto_fill_from_primary_category(self):
        related = self._related(self.isadora)
        self.assertEqual(len(related), 8)
        self.assertNotIn(self.isadora, related)
        self.assertNotIn(self.bath_sold_out, related)
        for p in related:
            self.assertIn(self.bath, p.categories.all())

        html = self.client.get(self.isadora.get_absolute_url()).content.decode()
        self.assertIn("Схожі товари, які вам можуть сподобатися", html)
        self.assertIn(f'href="{related[0].get_absolute_url()}"', html)

    def test_manual_related_wins(self):
        from catalog.models import RelatedProduct

        RelatedProduct.objects.create(related_to=self.isadora, product=self.door_mat)
        self.assertEqual(self._related(self.isadora), [self.door_mat])

    def test_small_category_uses_what_it_has(self):
        # «Під двері» has only this product: nothing to suggest, no empty slider.
        self.assertEqual(self._related(self.door_mat), [])
        html = self.client.get(self.door_mat.get_absolute_url()).content.decode()
        self.assertNotIn("Схожі товари, які вам можуть сподобатися", html)

    def test_spec_links_use_primary_category(self):
        from catalog.models import ProductSpecification, Specification, SpecificationValue

        spec = Specification.objects.create(title="Матеріал")
        value = SpecificationValue.objects.create(specification=spec, title="Поліпропілен")
        ProductSpecification.objects.create(
            product=self.isadora, specification=spec, spec_value=value
        )
        html = self.client.get(self.isadora.get_absolute_url()).content.decode()
        self.assertIn('data-category-slug="dlia-vanni"', html)


class CategoryGuidesTests(_CatalogFixture):
    def setUp(self):
        from blog.models import Article, ArticleTopic

        # Data migrations seed (and schedule) real articles; they would turn
        # public as the calendar moves and reshuffle the "newest" here.
        Article.objects.all().delete()
        now = timezone.now()

        def article(title, days_ago, body="<p>Текст.</p>", status=Article.Status.PUBLISHED):
            return Article.objects.create(
                title=title,
                status=status,
                published_at=now - timedelta(days=days_ago),
                description=body,
            )

        self.newest = [article(f"Свіжа стаття {i}", i + 1) for i in range(3)]
        self.door_article = article(
            "Килимок під двері: гумовий чи ворсовий",
            30,
            '<p>Дивіться <a href="/catalog/categorie/pid-dveri/">килимки під двері</a>.</p>',
        )
        self.bath_topic_article = article("Килимок у ванну", 40)
        ArticleTopic.objects.create(
            title="Ванна", target_path="/catalog/categorie/dlia-vanni/", article=self.bath_topic_article
        )
        self.door_draft = article(
            "Чернетка про двері",
            1,
            '<a href="/catalog/categorie/pid-dveri/">x</a>',
            status=Article.Status.DRAFT,
        )

    def test_article_linking_category_comes_first_even_if_older(self):
        from project.seo_content import get_seo_guides

        guides = get_seo_guides(self.door)
        self.assertEqual(len(guides), 3)
        self.assertEqual(guides[0], self.door_article)
        self.assertEqual(guides[1:], self.newest[:2])
        self.assertNotIn(self.door_draft, guides)

    def test_topic_target_path_counts(self):
        from project.seo_content import get_seo_guides

        self.assertEqual(get_seo_guides(self.bath)[0], self.bath_topic_article)

    def test_without_category_newest(self):
        from project.seo_content import get_seo_guides

        self.assertEqual(get_seo_guides(), self.newest)
        self.assertEqual(len(get_seo_guides(limit=10)), 5)

    def test_category_page_renders_its_articles(self):
        response = self.client.get(self.door.get_absolute_url())
        self.assertEqual(response.context["seo_guides"][0], self.door_article)
        self.assertContains(response, self.door_article.get_absolute_url())
        # «Вся колекція» stays the newest three.
        response = self.client.get("/catalog/collection/")
        self.assertEqual(response.context["seo_guides"], self.newest)


class ArticleCatalogButtonTests(_CatalogFixture):
    def _article(self, body):
        from blog.models import Article

        return Article.objects.create(
            title="Стаття про килими",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now() - timedelta(days=1),
            description=body,
        )

    def test_button_leads_to_linked_category(self):
        article = self._article(
            '<p><a href="/catalog/categorie/nema-takoi/">x</a> '
            '<a href="https://mrcarpet24.com/catalog/categorie/pid-dveri/">під двері</a></p>'
        )
        html = self.client.get(article.get_absolute_url()).content.decode()
        self.assertIn(
            '<a href="/catalog/categorie/pid-dveri/" class="bl-button bl-button--full">Перейти в каталог</a>',
            html,
        )

    def test_button_falls_back_to_catalog(self):
        article = self._article("<p>Без посилань.</p>")
        html = self.client.get(article.get_absolute_url()).content.decode()
        self.assertIn(
            '<a href="/catalog/" class="bl-button bl-button--full">Перейти в каталог</a>', html
        )

    def test_button_uses_topic_target(self):
        from blog.models import ArticleTopic
        from blog.views import catalog_cta_url

        article = self._article("<p>Без посилань.</p>")
        ArticleTopic.objects.create(
            title="Ванна", target_path="/catalog/categorie/dlia-vanni", article=article
        )
        self.assertEqual(catalog_cta_url(article), "/catalog/categorie/dlia-vanni/")
