"""Default listing order: one kind of product must not fill page 1.

Audit 24.11.2026 (C1/T4): 11 of the first 12 cards on «Турецькі» and 12 of 12
on «Вся колекція» were bath mats 60x100, because they were the newest batch.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from catalog.models import Product, ProductAttribute, ProductCategory, Size
from catalog.ordering import diversified, has_explicit_sort


class ListingOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.turkish = ProductCategory.objects.create(title="Турецькі", slug="turetski")
        cls.bath = ProductCategory.objects.create(title="Для ванни", slug="dlia-vanni")
        cls.kids = ProductCategory.objects.create(title="В дитячу", slug="v-ditiachu")
        small = Size.objects.create(title="0.6 x 1.0")
        big = Size.objects.create(title="2.0 x 3.0")
        now = timezone.now()
        cls.rugs, cls.mats = [], []

        def make(title, slug, size, price, cats, age_days, qty=2, image=None):
            p = Product.objects.create(title=title, slug=slug)
            if image is not None:
                p.image = image
                p.save()
            ProductAttribute.objects.create(product=p, size=size, price=price, quantity=qty)
            # after the attribute: its save() saves the product again
            Product.admin_objects.filter(pk=p.pk).update(
                created=now - timedelta(days=age_days)
            )
            p.categories.add(*cats)
            return p

        # 14 older rugs, then 14 newer bath mats: the batch that broke page 1.
        for i in range(14):
            cls.rugs.append(
                make(f"Килим {i}", f"rug-{i}", big, 3000 + i, [cls.turkish], 30 + i,
                     image="products/rug.jpg")
            )
        for i in range(14):
            cls.mats.append(
                make(f"Килимок {i}", f"mat-{i}", small, 600, [cls.turkish, cls.bath], i,
                     image="products/mat.jpg")
            )
        cls.kid = make("Дитячий килим", "kid-1", big, 2000, [cls.turkish, cls.kids], 50,
                       image="products/kid.jpg")
        cls.oos = make("Килим новий без залишку", "rug-oos", big, 3500, [cls.turkish], 0,
                       qty=0, image="products/oos.jpg")
        cls.noname = make("Килим 0010 без назви", "rug-noname", big, 3100, [cls.turkish], 1,
                          image="products/x.jpg")

    def _page1(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        return list(resp.context["products"])

    def test_turkish_page_one_is_mostly_rugs(self):
        page = self._page1(self.turkish.get_absolute_url())
        self.assertEqual(len(page), 12)
        mats = {p.pk for p in self.mats}
        non_bath = [p for p in page if p.pk not in mats]
        self.assertGreaterEqual(len(non_bath), 8)
        # still some newest mats on page 1, not hidden on the last page
        self.assertGreaterEqual(len(page) - len(non_bath), 2)
        # newest rug leads, the kids rug (another kind) takes an early turn
        self.assertEqual(page[0].pk, self.rugs[0].pk)
        self.assertIn(self.kid.pk, [p.pk for p in page[:3]])

    def test_collection_page_one_is_mixed(self):
        page = self._page1("/catalog/collection/")
        mats = {p.pk for p in self.mats}
        self.assertGreaterEqual(len([p for p in page if p.pk not in mats]), 8)

    def test_home_products_are_mixed(self):
        resp = self.client.get("/")
        products = list(resp.context["products"])[:12]
        mats = {p.pk for p in self.mats}
        self.assertGreaterEqual(len([p for p in products if p.pk not in mats]), 8)

    def test_bath_category_keeps_newest_first(self):
        page = self._page1(self.bath.get_absolute_url())
        self.assertEqual([p.pk for p in page], [p.pk for p in self.mats[:12]])

    def test_out_of_stock_and_unnamed_go_last(self):
        ordered = list(diversified(self.turkish.products.all()))
        self.assertEqual(ordered[-1].pk, self.oos.pk)
        self.assertEqual(ordered[-2].pk, self.noname.pk)

    def test_pages_do_not_overlap_and_cover_everything(self):
        url = self.turkish.get_absolute_url()
        seen = []
        for page in (1, 2, 3):
            resp = self.client.get(url, {"page": page})
            seen += [p.pk for p in resp.context["products"]]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), set(self.turkish.products.values_list("pk", flat=True)))

    def test_explicit_sort_still_wins(self):
        resp = self.client.get(self.turkish.get_absolute_url(), {"sort": "price"})
        prices = [p.product_attr.first().get_total_price() for p in resp.context["products"]]
        self.assertEqual(prices, sorted(prices))
        resp = self.client.get("/catalog/collection/", {"sort": "-price"})
        prices = [p.product_attr.first().get_total_price() for p in resp.context["products"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_filters_keep_working_with_default_order(self):
        resp = self.client.get(self.turkish.get_absolute_url(), {"price_min": "2500"})
        self.assertEqual(resp.status_code, 200)
        mats = {p.pk for p in self.mats}
        self.assertFalse([p for p in resp.context["products"] if p.pk in mats])

    def test_has_explicit_sort(self):
        self.assertFalse(has_explicit_sort({}))
        self.assertFalse(has_explicit_sort({"sort": "", "page": "2"}))
        self.assertTrue(has_explicit_sort({"sort": "title"}))
        self.assertTrue(has_explicit_sort({"price": "-product_attr__price"}))

    def test_catalog_preview_is_mixed(self):
        """/catalog/ shows 8 cards per category: mostly rugs on «Турецькі»."""
        import re

        html = self.client.get("/catalog/").content.decode()
        start = html.index('data-ga-list-id="catalog_turetski"')
        end = html.find("catalog_section_more", start)
        ids = [int(x) for x in re.findall(r'data-catalog-product-id="(\d+)"', html[start:end])]
        self.assertEqual(len(ids), 8)
        rugs = {p.pk for p in self.rugs} | {self.kid.pk}
        self.assertGreaterEqual(len([pk for pk in ids if pk in rugs]), 5)
