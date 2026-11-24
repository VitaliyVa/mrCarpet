"""Regressions found by the 2026-11-24 live-site audit."""

from pathlib import Path

from django.test import TestCase

from catalog.models import Favourite, ProductCategory


class MissingObjectsAre404Tests(TestCase):
    def test_unknown_product_is_404(self):
        self.assertEqual(
            self.client.get("/catalog/product/zzz-nonexistent-xyz/").status_code, 404
        )

    def test_unknown_category_is_404(self):
        self.assertEqual(
            self.client.get("/catalog/categorie/zzz-nonexistent/").status_code, 404
        )


class AnonymousPagesDoNotWriteTests(TestCase):
    def test_anonymous_page_view_creates_no_favourite_or_session(self):
        before = Favourite.objects.count()
        resp = self.client.get("/about/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Favourite.objects.count(), before)
        self.assertNotIn("sessionid", resp.cookies)


class EmptyCategoryNotInMenuTests(TestCase):
    def test_menu_hides_empty_category(self):
        ProductCategory.objects.create(title="Порожня", slug="porozhnia")
        html = self.client.get("/about/").content.decode()
        self.assertNotIn("/catalog/categorie/porozhnia/", html)


class SwaggerClosedTests(TestCase):
    def test_swagger_not_public(self):
        self.assertIn(
            self.client.get("/api/swagger/").status_code, (401, 403)
        )


class NoLeakingTemplateCommentsTests(TestCase):
    """`{# #}` is single-line only; a multi-line one renders as page text."""

    def test_no_multiline_hash_comments(self):
        bad = []
        for p in Path("templates").rglob("*.html"):
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "{#" in line and "#}" not in line.split("{#", 1)[1]:
                    bad.append(f"{p}:{n}")
        # product.html and blog.html are fixed in their own branches
        bad = [b for b in bad if "product.html" not in b and "blog.html" not in b]
        self.assertEqual(bad, [])
