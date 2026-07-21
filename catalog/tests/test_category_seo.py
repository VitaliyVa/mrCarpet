"""
Category pages have to say what they sell.

Titles are stored the way they read in a menu — "Українські", "В дитячу" —
because the surrounding page supplies the noun. A <title> has no surrounding
page, so these went out as "Українські | mr.Carpet": a page about something
Ukrainian that never says what. It could not rank for "українські килими"
because the word was absent.
"""

from django.test import TestCase

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
