"""
Category pages have to say what they sell.

Titles are stored the way they read in a menu — "Українські", "В дитячу" —
because the surrounding page supplies the noun. A <title> has no surrounding
page, so these went out as "Українські | mr.Carpet": a page about something
Ukrainian that never says what. It could not rank for "українські килими"
because the word was absent.
"""

from django.test import TestCase, override_settings

from catalog.templatetags.catalog_filters import (
    category_meta_description,
    category_phrase,
)


class CategoryPhraseTests(TestCase):
    def test_adjective_takes_the_noun_after_it(self):
        self.assertEqual(category_phrase("Українські"), "Українські килими")
        self.assertEqual(category_phrase("Турецькі"), "Турецькі килими")

    def test_preposition_puts_the_noun_first(self):
        """"В дитячу килими" is not Ukrainian; the noun has to lead."""
        self.assertEqual(category_phrase("В дитячу"), "Килими в дитячу")
        self.assertEqual(category_phrase("Для ванни"), "Килими для ванни")
        self.assertEqual(category_phrase("Під двері"), "Килими під двері")
        self.assertEqual(category_phrase("В кухню"), "Килими в кухню")

    def test_a_title_that_already_says_it_is_left_alone(self):
        """Otherwise: "Акрилові килими килими"."""
        self.assertEqual(category_phrase("Акрилові килими"), "Акрилові килими")

    def test_case_does_not_decide(self):
        self.assertEqual(category_phrase("акрилові КИЛИМИ"), "акрилові КИЛИМИ")

    def test_empty_stays_empty(self):
        self.assertEqual(category_phrase(""), "")
        self.assertEqual(category_phrase(None), "")

    def test_every_real_category_gains_the_noun(self):
        """The seven categories that actually exist, as of 2026-07-21."""
        for title in (
            "Українські",
            "Турецькі",
            "В дитячу",
            "Для ванни",
            "Акрилові килими",
            "Під двері",
            "В кухню",
        ):
            self.assertIn("килим", category_phrase(title).lower(), title)


class CategoryDescriptionTests(TestCase):
    def test_description_leads_with_the_searched_phrase(self):
        """Google truncates near 160 characters and readers scan the front,
        so the shop name must not come first."""

        class Fake:
            title = "Українські"

        desc = category_meta_description(Fake())
        self.assertTrue(desc.startswith("Українські килими"), desc)
        self.assertLessEqual(len(desc), 200)

    def test_missing_title_still_yields_something_usable(self):
        class Fake:
            title = ""

        self.assertIn("Килими", category_meta_description(Fake()))


@override_settings(SEO_INDEXING_ENABLED=True)
class EmptyCategoryTests(TestCase):
    """
    A category with no products is a page that shows nothing.

    Both "Для ванни" and "Акрилові килими" were live, indexable and listed in
    the sitemap with zero products — an invitation to index thin content, and
    a wasted visit for anyone who found it.
    """

    def setUp(self):
        # Without this the whole site is noindex and the test proves nothing.
        from catalog.models import Product, ProductCategory

        from catalog.models import ProductAttribute, Size

        self.empty = ProductCategory.objects.create(title="Порожня", slug="porozhnia")
        self.filled = ProductCategory.objects.create(title="Повна", slug="povna")

        # A real, buyable product: the default manager hides ones with no
        # stocked variant, so "has products" here means the same thing a
        # visitor sees rather than a bare row in the table.
        product = Product.objects.create(title="Килим", slug="kylym-cat")
        size = Size.objects.create(title="1.6 x 2.3")
        ProductAttribute.objects.create(
            product=product, size=size, price=1000, quantity=4
        )
        product.categories.add(self.filled)

    def test_empty_category_is_noindex(self):
        html = self.client.get(self.empty.get_absolute_url()).content.decode()
        self.assertIn('name="robots" content="noindex', html)

    def test_filled_category_stays_indexable(self):
        html = self.client.get(self.filled.get_absolute_url()).content.decode()
        self.assertNotIn("noindex", html)

    def test_empty_category_is_not_in_the_sitemap(self):
        from project.sitemaps import CategorySitemap

        slugs = {c.slug for c in CategorySitemap().items()}
        self.assertIn(self.filled.slug, slugs)
        self.assertNotIn(self.empty.slug, slugs)

    def test_it_returns_on_its_own_once_filled(self):
        """No manual step to undo — adding a product is enough."""
        from catalog.models import Product
        from project.sitemaps import CategorySitemap

        from catalog.models import ProductAttribute, Size

        product = Product.objects.create(title="Другий", slug="drugyi-cat")
        size = Size.objects.create(title="2 x 3")
        ProductAttribute.objects.create(
            product=product, size=size, price=900, quantity=2
        )
        product.categories.add(self.empty)

        slugs = {c.slug for c in CategorySitemap().items()}
        self.assertIn(self.empty.slug, slugs)
