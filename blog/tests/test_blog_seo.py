"""
Blog: drafts stay private, published URLs stay put.

Two of these guard the whole catalogue, not just the blog. The slug used to
be rebuilt from the title on every save, so correcting a typo in a product
name silently changed its URL — breaking whatever Google had indexed and any
link a customer had shared.
"""

from django.test import TestCase
from django.urls import reverse

from blog.models import Article
from catalog.models import Product


class SlugStabilityTests(TestCase):
    def test_slug_survives_a_title_edit(self):
        article = Article.objects.create(title="Як вибрати килим")
        original = article.slug
        self.assertTrue(original)

        article.title = "Як вибрати килим у вітальню"
        article.save()
        article.refresh_from_db()
        self.assertEqual(article.slug, original)

    def test_products_keep_their_url_too(self):
        """The same save() backs every slugged model in the shop."""
        product = Product.objects.create(title="Килим Мira")
        original = product.slug

        product.title = "Килим Mira 24058"
        product.save()
        product.refresh_from_db()
        self.assertEqual(product.slug, original)

    def test_a_blank_slug_is_still_generated(self):
        article = Article.objects.create(title="Чим чистити килим")
        self.assertTrue(article.slug)

    def test_clearing_the_slug_regenerates_it(self):
        """The deliberate escape hatch for a genuine rename."""
        article = Article.objects.create(title="Стара назва")
        article.title = "Нова назва"
        article.slug = ""
        article.save()
        article.refresh_from_db()
        self.assertIn("nova", article.slug)

    def test_update_fields_is_honoured(self):
        """save() dropped its arguments, quietly forcing a full-row write."""
        article = Article.objects.create(title="Тест")
        article.title = "Змінено"
        article.save(update_fields=["title", "updated"])
        article.refresh_from_db()
        self.assertEqual(article.title, "Змінено")


class DraftVisibilityTests(TestCase):
    def setUp(self):
        self.draft = Article.objects.create(title="Чернетка", description="текст")
        self.live = Article.objects.create(
            title="Опублікована",
            description="текст",
            status=Article.Status.PUBLISHED,
        )

    def test_new_articles_start_as_drafts(self):
        """Saving used to publish instantly — including raw generator output."""
        self.assertEqual(self.draft.status, Article.Status.DRAFT)

    def test_list_shows_only_published(self):
        html = self.client.get(reverse("blog")).content.decode()
        self.assertIn("Опублікована", html)
        self.assertNotIn("Чернетка", html)

    def test_draft_detail_is_404_for_visitors(self):
        response = self.client.get(reverse("article", args=[self.draft.slug]))
        self.assertEqual(response.status_code, 404)

    def test_published_detail_opens(self):
        response = self.client.get(reverse("article", args=[self.live.slug]))
        self.assertEqual(response.status_code, 200)

    def test_draft_is_not_in_the_sitemap(self):
        from project.sitemaps import ArticleSitemap

        slugs = {a.slug for a in ArticleSitemap().items()}
        self.assertIn(self.live.slug, slugs)
        self.assertNotIn(self.draft.slug, slugs)

    def test_draft_is_not_cross_linked_from_categories(self):
        from project.seo_content import get_seo_guides

        titles = {a.title for a in get_seo_guides()}
        self.assertIn("Опублікована", titles)
        self.assertNotIn("Чернетка", titles)


class PublishDateTests(TestCase):
    def test_stamped_on_first_publish(self):
        article = Article.objects.create(title="Стаття")
        self.assertIsNone(article.published_at)

        article.status = Article.Status.PUBLISHED
        article.save()
        article.refresh_from_db()
        self.assertIsNotNone(article.published_at)

    def test_editing_later_does_not_move_the_date(self):
        """An article that keeps claiming to be new reads as churn."""
        article = Article.objects.create(
            title="Стаття", status=Article.Status.PUBLISHED
        )
        article.refresh_from_db()
        stamped = article.published_at

        article.description = "доповнено"
        article.save()
        article.refresh_from_db()
        self.assertEqual(article.published_at, stamped)

    def test_markup_uses_the_publish_date(self):
        from django.test import RequestFactory

        from project.seo_jsonld import article_graph

        article = Article.objects.create(
            title="Стаття", status=Article.Status.PUBLISHED
        )
        article.refresh_from_db()
        request = RequestFactory().get("/", HTTP_HOST="mrcarpet24.com")
        data = article_graph(request, article)
        self.assertEqual(
            data["datePublished"], article.published_at.isoformat()
        )


class ListPageTests(TestCase):
    def test_list_carries_canonical_and_breadcrumbs(self):
        Article.objects.create(title="Стаття", status=Article.Status.PUBLISHED)
        html = self.client.get(reverse("blog")).content.decode()
        self.assertIn('rel="canonical"', html)
        self.assertIn("BreadcrumbList", html)

    def test_pagination_splits_the_list(self):
        from blog.views import PER_PAGE

        for i in range(PER_PAGE + 3):
            Article.objects.create(
                title=f"Стаття {i}", status=Article.Status.PUBLISHED
            )
        first = self.client.get(reverse("blog")).context["page_obj"]
        self.assertEqual(len(first.object_list), PER_PAGE)
        self.assertTrue(first.has_next())

    def test_empty_blog_says_so(self):
        html = self.client.get(reverse("blog")).content.decode()
        self.assertIn("Незабаром", html)
