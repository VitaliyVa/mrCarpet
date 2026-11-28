"""Catalog search (?q=): every word must match somewhere, sizes in cm work."""

from django.test import TestCase

from catalog.filters import ProductFilter, search_tokens, size_variants
from catalog.models import Product, ProductAttribute, Size


class SearchHelpersTests(TestCase):
    def test_size_variants_read_cm_and_metres(self):
        self.assertEqual(size_variants("200x300"), ["2.0х3.0", "2.0x3.0"])
        self.assertEqual(size_variants("2х3"), ["2.0х3.0", "2.0x3.0"])
        self.assertEqual(size_variants("67x120"), ["0.67х1.2", "0.67x1.2"])
        self.assertEqual(size_variants("сірий"), [])

    def test_tokens_drop_shop_words_and_join_spaced_sizes(self):
        self.assertEqual(search_tokens("Купити сірий килим 200 x 300"), ["сірий", "килим", "200x300"])


class SearchFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        big = Size.objects.create(title="2.0х3.0")
        small = Size.objects.create(title="0.8х1.5")
        cls.grey = Product.objects.create(title="Килим прямокутний сірий Mira", slug="grey")
        ProductAttribute.objects.create(product=cls.grey, size=big, price=3200, quantity=1)
        ProductAttribute.objects.create(product=cls.grey, size=small, price=800, quantity=1)
        cls.beige = Product.objects.create(title="Килим овальний бежевий Fashion", slug="beige")
        ProductAttribute.objects.create(product=cls.beige, size=small, price=700, quantity=1)

    def _search(self, q):
        return set(ProductFilter({"q": q}, Product.objects.all()).qs)

    def test_colour_and_size_together(self):
        self.assertEqual(self._search("сірий 200x300"), {self.grey})
        self.assertEqual(self._search("бежевий 200x300"), set())

    def test_word_forms(self):
        self.assertEqual(self._search("сірі килими"), {self.grey})
        self.assertEqual(self._search("овальна"), {self.beige})

    def test_shop_words_only_returns_everything(self):
        self.assertEqual(self._search("купити"), {self.grey, self.beige})
