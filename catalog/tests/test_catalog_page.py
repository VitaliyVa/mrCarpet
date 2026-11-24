from django.test import TestCase


class CatalogPreviewCapTests(TestCase):
    """/catalog/ shows a preview per category, not every product it has.

    Rendering whole categories made the page ~590 KB of HTML with 300+
    images and a multi-second server response on mobile.
    """

    def setUp(self):
        from catalog.models import Product, ProductAttribute, ProductCategory, Size

        self.big = ProductCategory.objects.create(title="Велика", slug="velyka")
        self.small = ProductCategory.objects.create(title="Мала", slug="mala")
        size = Size.objects.create(title="1 x 2")
        for i in range(11):
            p = Product.objects.create(title=f"Килим {i}", slug=f"kylym-cap-{i}")
            ProductAttribute.objects.create(product=p, size=size, price=100, quantity=1)
            p.categories.add(self.big)
            if i < 3:
                p.categories.add(self.small)

    def _sections(self):
        html = self.client.get("/catalog/").content.decode()
        return html.split('<div class="catalog_section">')[1:]

    def test_each_category_renders_at_most_eight_products(self):
        counts = {}
        for section in self._sections():
            for cat in (self.big, self.small):
                if f"<h2>{cat.title}</h2>" in section:
                    counts[cat.slug] = section.count("data-catalog-product-id=")
                    has_more = "Дивитись всі" in section
                    counts[cat.slug + ":more"] = has_more
        self.assertEqual(counts["velyka"], 8)
        self.assertTrue(counts["velyka:more"])
        self.assertEqual(counts["mala"], 3)
        self.assertFalse(counts["mala:more"])
