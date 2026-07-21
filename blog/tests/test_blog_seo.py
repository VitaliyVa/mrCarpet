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


class WeeklyTopicTests(TestCase):
    """
    The queue feeds the generator, and the generator stops at a draft.
    """

    def setUp(self):
        from blog.models import ArticleTopic

        self.first = ArticleTopic.objects.create(
            title="Найкраща тема", brief="про це", target_path="/catalog/", rank=1
        )
        ArticleTopic.objects.create(title="Друга", rank=2)

    def test_the_queue_is_ordered_best_first(self):
        from blog.models import ArticleTopic

        self.assertEqual(ArticleTopic.next_pending(), self.first)

    def test_a_used_topic_leaves_the_queue(self):
        """Otherwise next week rewrites the same article."""
        from blog.models import ArticleTopic

        self.first.status = ArticleTopic.Status.USED
        self.first.save()
        self.assertEqual(ArticleTopic.next_pending().title, "Друга")

    def test_generation_publishes(self):
        from unittest.mock import patch

        from blog.models import ArticleTopic
        from blog.services import weekly_topic

        article = Article.objects.create(title="Згенерована")

        class FakeResult:
            article_id = article.pk
            title = "Згенерована"

        with patch.object(
            weekly_topic, "_tell_staff"
        ), patch(
            "blog.services.article_generate.ReplicateArticleService.generate_and_create",
            return_value=FakeResult(),
        ):
            result = weekly_topic.generate_next()

        self.assertTrue(result["ok"])
        article.refresh_from_db()
        self.assertEqual(article.status, Article.Status.PUBLISHED)
        self.assertIsNotNone(article.published_at)

        self.first.refresh_from_db()
        self.assertEqual(self.first.status, ArticleTopic.Status.USED)
        self.assertEqual(self.first.article_id, article.pk)

    def test_the_brief_and_target_reach_the_generator(self):
        """A bare title produces something generic that links nowhere."""
        from unittest.mock import patch

        from blog.services import weekly_topic

        article = Article.objects.create(title="X")

        class FakeResult:
            article_id = article.pk
            title = "X"

        with patch.object(weekly_topic, "_tell_staff"), patch(
            "blog.services.article_generate.ReplicateArticleService.generate_and_create",
            return_value=FakeResult(),
        ) as gen:
            weekly_topic.generate_next()

        prompt = gen.call_args[0][0]
        self.assertIn("Найкраща тема", prompt)
        self.assertIn("про це", prompt)
        self.assertIn("/catalog/", prompt)

    def test_the_alert_carries_the_text_not_just_a_link(self):
        """
        The post is already live, so a link asks someone to go and check and
        nobody does. The opening lines in a chat already open are the whole
        review this pipeline gets.
        """
        from unittest.mock import patch

        from blog.services import weekly_topic

        article = Article.objects.create(
            title="Про килими",
            description="<p>Килим під ліжко 1,8 м має бути 3,0 м завширшки.</p>",
        )

        class FakeResult:
            article_id = article.pk
            title = "Про килими"

        with patch.object(weekly_topic, "_tell_staff") as tell, patch(
            "blog.services.article_generate.ReplicateArticleService.generate_and_create",
            return_value=FakeResult(),
        ):
            weekly_topic.generate_next()

        text = tell.call_args[0][0]
        self.assertIn("3,0 м завширшки", text)
        self.assertIn("опублікована", text)
        self.assertNotIn("<p>", text)

    def test_a_failed_generation_leaves_the_topic_queued(self):
        from unittest.mock import patch

        from blog.models import ArticleTopic
        from blog.services import weekly_topic

        with patch.object(weekly_topic, "_tell_staff"), patch(
            "blog.services.article_generate.ReplicateArticleService.generate_and_create",
            side_effect=RuntimeError("replicate down"),
        ):
            result = weekly_topic.generate_next()

        self.assertFalse(result["ok"])
        self.first.refresh_from_db()
        self.assertEqual(self.first.status, ArticleTopic.Status.PENDING)

    def test_an_empty_queue_is_not_a_crash(self):
        from unittest.mock import patch

        from blog.models import ArticleTopic
        from blog.services import weekly_topic

        ArticleTopic.objects.all().delete()
        with patch.object(weekly_topic, "_tell_staff") as tell:
            result = weekly_topic.generate_next()

        self.assertFalse(result["ok"])
        self.assertIn("порожня", tell.call_args[0][0])


class CatalogRealityTests(TestCase):
    """
    The article must not send readers where the shop has nothing.

    Both failures were real in the first five drafts: one recommended cotton
    and nylon rugs the catalogue has never carried, and two topics pointed at
    categories with zero products.
    """

    def setUp(self):
        from blog.models import ArticleTopic
        from catalog.models import (
            Product,
            ProductAttribute,
            ProductCategory,
            Size,
        )

        self.empty = ProductCategory.objects.create(title="Порожня", slug="porozhnia")
        self.filled = ProductCategory.objects.create(title="Повна", slug="povna")
        product = Product.objects.create(title="Килим", slug="kylym-blog")
        size = Size.objects.create(title="1.6 x 2.3")
        ProductAttribute.objects.create(
            product=product, size=size, price=1000, quantity=3
        )
        product.categories.add(self.filled)

        self.topic = ArticleTopic.objects.create(
            title="Тема",
            target_path="/catalog/categorie/porozhnia/",
            rank=1,
        )

    def test_empty_category_is_swapped_for_the_catalogue(self):
        from blog.services.weekly_topic import _usable_target

        self.assertEqual(
            _usable_target("/catalog/categorie/porozhnia/"), "/catalog/"
        )

    def test_a_stocked_category_is_kept(self):
        from blog.services.weekly_topic import _usable_target

        self.assertEqual(
            _usable_target("/catalog/categorie/povna/"),
            "/catalog/categorie/povna/",
        )

    def test_prompt_never_points_at_an_empty_category(self):
        from unittest.mock import patch

        from blog.services import weekly_topic

        article = Article.objects.create(title="X")

        class FakeResult:
            article_id = article.pk
            title = "X"

        with patch.object(weekly_topic, "_tell_staff"), patch(
            "blog.services.article_generate.ReplicateArticleService.generate_and_create",
            return_value=FakeResult(),
        ) as gen:
            weekly_topic.generate_next()

        prompt = gen.call_args[0][0]
        self.assertNotIn("porozhnia", prompt)
        self.assertIn("/catalog/", prompt)

    def test_prompt_lists_only_stocked_materials(self):
        from unittest.mock import patch

        from catalog.models import (
            ProductSpecification,
            Specification,
            SpecificationValue,
        )
        from blog.services import weekly_topic

        spec = Specification.objects.create(title="Склад килима")
        value = SpecificationValue.objects.create(title="Поліпропілен")
        product = Article.objects.none()  # placeholder, spec attaches below
        from catalog.models import Product

        ProductSpecification.objects.create(
            product=Product.objects.first(), specification=spec, spec_value=value
        )

        article = Article.objects.create(title="Y")

        class FakeResult:
            article_id = article.pk
            title = "Y"

        with patch.object(weekly_topic, "_tell_staff"), patch(
            "blog.services.article_generate.ReplicateArticleService.generate_and_create",
            return_value=FakeResult(),
        ) as gen:
            weekly_topic.generate_next()

        prompt = gen.call_args[0][0]
        self.assertIn("Поліпропілен", prompt)
        self.assertIn("Не радь шерсть", prompt)


class ArticleTypographyTests(TestCase):
    """
    Every tag that can reach the page has a style.

    The article body used to define only <p>, so headings, lists and links
    fell back to the global sheet and one article read as three documents
    stacked together. The sanitizer — not the prompt — is the real boundary:
    it permits h3 and em even though the prompt forbids them, and anything
    crossing it unstyled brings the problem back.
    """

    CSS = "static/source/pages/blog_inside/index.css"

    def _css(self):
        from pathlib import Path

        return Path(self.CSS).read_text(encoding="utf-8")

    def test_every_allowed_tag_is_styled(self):
        from blog.services.html_sanitize import ALLOWED_TAGS

        css = self._css()
        unstyled = [
            tag
            for tag in sorted(ALLOWED_TAGS)
            if f".blog-inside__block-text {tag}{{" not in css
            and f".blog-inside__block-text {tag}," not in css
            and f",.blog-inside__block-text {tag}{{" not in css
        ]
        self.assertEqual(
            unstyled,
            [],
            f"теги без стилю: {unstyled} — впадуть на глобальні правила",
        )

    def test_body_is_sized_for_reading(self):
        """20px at 130% put the lines close enough to blur over a screenful."""
        css = self._css()
        self.assertIn(
            ".blog-inside__block-text{color:#4a443f;font-size:18px;line-height:1.75}",
            css,
        )

    def test_compiled_css_matches_the_source(self):
        """
        webpack does not run on deploy, so editing only the SCSS ships
        nothing. This catches the half-applied change.
        """
        from pathlib import Path

        scss = Path(
            "static/development/components/pages/blog_inside/index.scss"
        ).read_text(encoding="utf-8")
        css = self._css()
        for marker in ("counter-reset: step", "border-left: 3px solid #a46c46"):
            self.assertIn(marker, scss)
        for marker in ("counter-reset:step", "border-left:3px solid #a46c46"):
            self.assertIn(marker, css)
