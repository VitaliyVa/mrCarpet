"""
Article component kit: what the sanitizer lets through, what the renderer
adds, and the live product cards.

The kit (docs/blog-components.md) is plain HTML with bl-* classes. The
sanitizer is the boundary: it must keep exactly the kit and strip the rest,
because article bodies come from a model and from editors pasting text.
"""

from django.test import TestCase
from django.urls import reverse

from blog.models import Article
from blog.services.article_render import render_article
from blog.services.html_sanitize import ALLOWED_CLASSES, sanitize_article_html
from blog.templatetags.blog_filters import article_body, uk_minutes


KIT = {
    "summary": '<div class="bl-summary"><p><strong>Коротко:</strong> так</p></div>',
    "tip": '<div class="bl-callout bl-callout--tip"><p>порада</p></div>',
    "note": '<div class="bl-callout bl-callout--note"><p>до відома</p></div>',
    "warning": '<div class="bl-callout bl-callout--warning"><p>увага</p></div>',
    "checklist": '<ul class="bl-checklist"><li>раз</li></ul>',
    "steps": '<ol class="bl-steps"><li><strong>Крок</strong>опис</li></ol>',
    "proscons": (
        '<div class="bl-proscons"><div class="bl-pros"><p class="bl-proscons__title">Плюси</p>'
        '<ul><li>a</li></ul></div><div class="bl-cons"><p class="bl-proscons__title">Мінуси</p>'
        "<ul><li>b</li></ul></div></div>"
    ),
    "table": (
        '<div class="bl-table"><table><thead><tr><th scope="col">A</th></tr></thead>'
        '<tbody><tr><td colspan="2">1</td></tr></tbody></table></div>'
    ),
    "figure": (
        '<figure class="bl-figure--wide"><img src="/media/a.webp" alt="Килим" width="800" '
        'height="600" loading="lazy" decoding="async"><figcaption>Підпис</figcaption></figure>'
    ),
    "gallery": (
        '<div class="bl-gallery bl-gallery--3"><figure><img src="https://mrcarpet24.com/media/b.webp" '
        'alt="" loading="lazy" decoding="async"></figure></div>'
    ),
    "quote": (
        '<blockquote class="bl-quote"><p>Беріть більший.</p>'
        '<p class="bl-quote__author">Команда mr.Carpet</p></blockquote>'
    ),
    "faq": '<div class="bl-faq"><details><summary>Питання?</summary><p>Так.</p></details></div>',
    "product": (
        '<a class="bl-product" href="/catalog/"><img class="bl-product__img" src="/media/c.webp" '
        'alt="" loading="lazy" decoding="async"><span class="bl-product__body">'
        '<span class="bl-product__title">Килими</span><span class="bl-product__text">опис</span>'
        '<span class="bl-product__price">від 900 грн</span>'
        '<span class="bl-product__more">Дивитись →</span></span></a>'
    ),
    "cta": (
        '<div class="bl-cta"><p class="bl-cta__title">Заголовок</p><p>Текст</p>'
        '<a class="bl-btn" href="/catalog/">Каталог</a></div>'
    ),
    "products": '<div class="blog-products" data-products="a-1,b-2"></div>',
}


class SanitizerAllowlistTests(TestCase):
    def test_every_component_survives_unchanged(self):
        for name, html in KIT.items():
            with self.subTest(component=name):
                self.assertEqual(sanitize_article_html(html), html)

    def test_kit_classes_are_exactly_the_documented_ones(self):
        """A class here without docs, or in docs without being allowed, is a bug."""
        from pathlib import Path

        doc = Path("docs/blog-components.md")
        if not doc.exists():  # docs/ is local-only (gitignored) in this repo
            self.skipTest("docs/blog-components.md not present in this checkout")
        text = doc.read_text(encoding="utf-8")
        for classes in ALLOWED_CLASSES.values():
            for cls in classes:
                with self.subTest(cls=cls):
                    self.assertIn(cls, text)

    def test_unknown_classes_are_stripped(self):
        out = sanitize_article_html('<div class="bl-cta header fixed"><p class="evil">x</p></div>')
        self.assertEqual(out, '<div class="bl-cta"><p>x</p></div>')

    def test_div_without_kit_class_keeps_no_class(self):
        self.assertEqual(sanitize_article_html('<div class="modal">x</div>'), "<div>x</div>")

    def test_scripts_and_handlers_are_dropped_with_their_text(self):
        out = sanitize_article_html(
            '<p onclick="x()">a</p><script>alert(1)</script><style>p{}</style>'
            '<iframe src="https://evil">frame</iframe><b>b</b>'
        )
        self.assertEqual(out, "<p>a</p>b")

    def test_dangerous_urls_are_removed(self):
        out = sanitize_article_html(
            '<a href="javascript:alert(1)">x</a>'
            '<img src="javascript:alert(1)"><img src="data:image/png;base64,AAA">'
            '<img src="//evil.example/x.png"><img src="http://plain.example/x.png">'
        )
        self.assertEqual(out, "<a>x</a>")

    def test_img_gets_lazy_loading_and_alt(self):
        out = sanitize_article_html('<img src="/media/x.webp" onerror="x()">')
        self.assertEqual(out, '<img src="/media/x.webp" alt="" loading="lazy" decoding="async">')

    def test_numeric_attrs_must_be_numbers(self):
        out = sanitize_article_html('<img src="/m.webp" width="100%" height="300">')
        self.assertIn('height="300"', out)
        self.assertNotIn("width", out)

    def test_stray_closing_tags_cannot_escape_the_body(self):
        """A stray </div> would close the page wrapper and drag the sidebar in."""
        out = sanitize_article_html("<p>a</p></div></div><div><p>b")
        self.assertEqual(out, "<p>a</p><div><p>b</p></div>")

    def test_products_slug_list_is_cleaned(self):
        out = sanitize_article_html(
            '<div data-products="Rug-1, rug_2,<x>,  " class="blog-products extra"></div>'
        )
        self.assertEqual(out, '<div class="blog-products" data-products="rug-1,rug_2,x"></div>')

    def test_data_products_only_on_the_placeholder(self):
        out = sanitize_article_html('<div class="bl-cta" data-products="a">x</div>')
        self.assertEqual(out, '<div class="bl-cta">x</div>')

    def test_old_articles_render_as_before(self):
        old = (
            "<p><strong>Коротко:</strong> так.</p><h2>Що?</h2><p>Текст з "
            '<a href="/catalog/" title="t">лінком</a>.</p><ul><li>a</li></ul>'
        )
        self.assertEqual(sanitize_article_html(old), old)


class RenderTests(TestCase):
    def test_h2_get_ids_and_feed_the_contents(self):
        parts = render_article("<p>Вступ</p><h2>Який розмір?</h2><p>x</p><h2>Який розмір?</h2>")
        self.assertEqual(
            [item["id"] for item in parts.toc], ["iakii-rozmir", "iakii-rozmir-2"]
        )
        self.assertIn('<h2 id="iakii-rozmir">Який розмір?</h2>', parts.body)

    def test_korotko_opener_gets_the_summary_box(self):
        parts = render_article("<p><strong>Коротко:</strong> так.</p><h2>Що?</h2>")
        # split off as the lead so the page can show it above the cover
        self.assertTrue(
            parts.lead.startswith('<div class="bl-summary"><p><strong>Коротко:</strong>')
        )

    def test_summary_is_not_wrapped_twice(self):
        html = '<div class="bl-summary"><p><strong>Коротко:</strong> так.</p></div>'
        parts = render_article(html)
        self.assertEqual((parts.lead + parts.body).count("bl-summary"), 1)

    def test_bare_tables_get_a_scroller(self):
        body = render_article("<p>x</p><table><tr><td>1</td></tr></table>").body
        self.assertIn('<div class="bl-table"><table>', body)
        wrapped = '<p>x</p><div class="bl-table"><table><tr><td>1</td></tr></table></div>'
        self.assertEqual(render_article(wrapped).body.count("bl-table"), 1)

    def test_reading_time(self):
        words = " ".join(["слово"] * 400)
        self.assertEqual(render_article(f"<p>{words}</p>").minutes, 3)
        self.assertEqual(render_article("<p>коротко</p>").minutes, 1)

    def test_plain_text_body_still_works(self):
        parts = render_article("Перший рядок\n\nДругий")
        self.assertIn("<p>Перший рядок</p>", parts.body)

    def test_minutes_wording(self):
        self.assertEqual(uk_minutes(1), "1 хвилина")
        self.assertEqual(uk_minutes(3), "3 хвилини")
        self.assertEqual(uk_minutes(5), "5 хвилин")
        self.assertEqual(uk_minutes(12), "12 хвилин")
        self.assertEqual(uk_minutes(22), "22 хвилини")


class LiveProductCardsTests(TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path

        from django.test import override_settings

        from catalog.models import Product, ProductAttribute, Size

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        (Path(media) / "products").mkdir()
        (Path(media) / "products" / "akva.webp").write_bytes(b"RIFF0000WEBP")
        media_override = override_settings(MEDIA_ROOT=media)
        media_override.enable()
        self.addCleanup(media_override.disable)

        size_a = Size.objects.create(title="1.6 x 2.3")
        size_b = Size.objects.create(title="2.0 x 2.9")

        self.cheap = Product.objects.create(
            title="Килим Аква", slug="kylym-akva", image="products/akva.webp"
        )
        ProductAttribute.objects.create(product=self.cheap, size=size_a, price=2000, quantity=2)
        ProductAttribute.objects.create(
            product=self.cheap, size=size_b, price=3000, quantity=1, discount=10
        )

        self.gone = Product.objects.create(title="Килим Сірий", slug="kylym-siryi")
        ProductAttribute.objects.create(product=self.gone, size=size_a, price=1500, quantity=0)

        # No variations at all: the catalogue hides it, so must the article.
        Product.objects.create(title="Прихований", slug="kylym-hidden")

    def _render(self, slugs):
        return str(article_body(f'<p>Вступ</p><div class="blog-products" data-products="{slugs}"></div>'))

    def test_two_valid_and_one_bogus_slug(self):
        html = self._render("kylym-akva,no-such-rug,kylym-siryi")
        self.assertEqual(html.count('class="blog-products__card'), 2)
        self.assertIn(reverse("product", args=["kylym-akva"]), html)
        self.assertIn(reverse("product", args=["kylym-siryi"]), html)
        self.assertNotIn("no-such-rug", html)
        self.assertIn("blog-products--2", html)
        # cheapest in-stock size, «від» because there are several sizes
        self.assertIn("від 2 000 грн", html)
        # the discount sits on a bigger size, so the badge says «до»
        self.assertIn("до −10%", html)
        # out of stock is shown, not hidden
        self.assertIn("is-oos", html)
        self.assertIn("Немає в наявності", html)
        # images are lazy with fixed dimensions; a missing file gets a placeholder
        self.assertIn("/media/products/akva.webp", html)
        self.assertIn('loading="lazy"', html)
        self.assertIn("blog-products__noimg", html)
        self.assertIn('width="365" height="420"', html)
        # author order is kept
        self.assertLess(html.index("Килим Аква"), html.index("Килим Сірий"))

    def test_block_disappears_when_nothing_is_valid(self):
        html = self._render("no-such-rug,kylym-hidden")
        self.assertEqual(html, "<p>Вступ</p>")

    def test_at_most_four_cards(self):
        from blog.services.product_cards import parse_slugs

        self.assertEqual(parse_slugs("a,b,c,d,e"), ["a", "b", "c", "d"])
        self.assertEqual(parse_slugs("a, a ,B"), ["a", "b"])

    def test_cards_render_on_the_article_page(self):
        article = Article.objects.create(
            title="Стаття з товарами",
            status=Article.Status.PUBLISHED,
            description=(
                "<p><strong>Коротко:</strong> так.</p><h2>Що купити?</h2>"
                '<div class="blog-products" data-products="kylym-akva"></div>'
            ),
        )
        html = self.client.get(article.get_absolute_url()).content.decode()
        self.assertIn("blog-products__card", html)
        self.assertIn("Килим Аква", html)


class PageTests(TestCase):
    def setUp(self):
        self.article = Article.objects.create(
            title="Килимок у ванну: як вибрати",
            status=Article.Status.PUBLISHED,
            description=(
                "<p><strong>Коротко:</strong> так.</p><h2>Перше питання?</h2><p>x</p>"
                "<h2>Друге питання?</h2><p>y</p>"
            ),
        )
        Article.objects.create(
            title="Чим чистити килим", status=Article.Status.PUBLISHED, description="<p>z</p>"
        )

    def test_article_page_has_contents_meta_share_and_related(self):
        html = self.client.get(self.article.get_absolute_url()).content.decode()
        self.assertIn('href="#pershe-pitannia"', html)
        self.assertIn("хвилин", html)
        self.assertIn("t.me/share/url", html)
        self.assertIn("Читайте також", html)
        self.assertIn("Чим чистити килим", html)
        self.assertIn('property="article:published_time"', html)
        self.assertIn('property="article:modified_time"', html)

    def test_list_has_topics_and_featured_card(self):
        html = self.client.get(reverse("blog")).content.decode()
        self.assertIn("bl-card--featured", html)
        self.assertIn("bl-chips", html)
        self.assertIn("Килим у кімнату", html)
        self.assertIn("Догляд і чистка", html)

    def test_topic_filter(self):
        response = self.client.get(reverse("blog") + "?tema=doglyad")
        titles = [a.title for a in response.context["cards"]]
        self.assertEqual(titles, ["Чим чистити килим"])
        # a filtered view points canonical at the whole list
        import re

        canonical = re.search(r'rel="canonical" href="([^"]+)"', response.content.decode()).group(1)
        self.assertTrue(canonical.endswith("/blog/"), canonical)

    def test_unknown_topic_shows_everything(self):
        response = self.client.get(reverse("blog") + "?tema=nonsense")
        self.assertIsNone(response.context["active_topic"])
        self.assertIsNotNone(response.context["featured"])

    def test_no_multiline_hash_comments_in_blog_templates(self):
        """Django renders a multi-line {# #} as text, straight into the page."""
        import re
        from pathlib import Path

        for name in ("blog.html", "blog_inside.html", "includes/blog_card.html",
                     "includes/blog_share.html", "includes/blog_products.html"):
            text = Path("templates", name).read_text(encoding="utf-8")
            with self.subTest(template=name):
                self.assertIsNone(re.search(r"\{#(?:(?!#\}).)*\n", text, re.S))
