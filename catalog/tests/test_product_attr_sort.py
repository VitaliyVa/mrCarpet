from decimal import Decimal

from django.test import TestCase

from catalog.models import Product, ProductAttribute, Size
from catalog.services.product_attr_sort import (
    ordered_size_queryset,
    product_attr_sort_key,
    reorder_product_attributes,
    size_first_number,
)


class SizeFirstNumberTests(TestCase):
    def test_wxh(self):
        self.assertEqual(size_first_number("100x200"), Decimal("100"))
        self.assertEqual(size_first_number("1,5x2.0"), Decimal("1.5"))
        self.assertEqual(size_first_number("50x50"), Decimal("50"))

    def test_diameter(self):
        self.assertEqual(size_first_number("∅ 67 см"), Decimal("67"))

    def test_no_number(self):
        self.assertIsNone(size_first_number("Маленький"))
        self.assertIsNone(size_first_number(""))
        self.assertIsNone(size_first_number(None))


class ReorderProductAttributesTests(TestCase):
    def setUp(self):
        self.product = Product.admin_objects.create(title="Sort Test Rug")

    def _size(self, title):
        return Size.objects.create(title=title)

    def _attr(self, size_title, *, custom=False, sort_order=0, quantity=1, price=100):
        return ProductAttribute.objects.create(
            product=self.product,
            size=self._size(size_title) if size_title else None,
            quantity=quantity,
            price=price,
            custom_attribute=custom,
            sort_order=sort_order,
        )

    def test_reorder_by_width_asc(self):
        a200 = self._attr("200x200", sort_order=10)
        a50 = self._attr("50x50", sort_order=20)
        a100 = self._attr("100x100", sort_order=30)

        changed = reorder_product_attributes(self.product)
        self.assertGreater(changed, 0)

        a50.refresh_from_db()
        a100.refresh_from_db()
        a200.refresh_from_db()
        self.assertEqual(a50.sort_order, 10)
        self.assertEqual(a100.sort_order, 20)
        self.assertEqual(a200.sort_order, 30)

        ordered = list(
            self.product.product_attr.order_by("sort_order", "id").values_list(
                "size__title", flat=True
            )
        )
        self.assertEqual(ordered, ["50x50", "100x100", "200x200"])

    def test_custom_and_unparseable_last(self):
        custom = self._attr(None, custom=True)
        named = self._attr("Середній")
        sized = self._attr("80x120")

        reorder_product_attributes(self.product)

        keys = [
            product_attr_sort_key(a)
            for a in self.product.product_attr.select_related("size")
        ]
        keys.sort()
        # fixed with number, then unparseable fixed, then custom
        ordered_pks = [k[-1] for k in keys]
        self.assertEqual(ordered_pks, [sized.pk, named.pk, custom.pk])


class OrderedSizeQuerysetTests(TestCase):
    def test_select_options_by_width(self):
        Size.objects.create(title="200x200")
        Size.objects.create(title="Маленький")
        Size.objects.create(title="50x50")
        Size.objects.create(title="100x100")
        Size.objects.create(title="∅ 67 см")

        titles = list(ordered_size_queryset().values_list("title", flat=True))
        self.assertEqual(
            titles,
            ["50x50", "∅ 67 см", "100x100", "200x200", "Маленький"],
        )
