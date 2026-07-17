from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from catalog.admin_forms import (
    DEFAULT_CATALOG_IMAGE,
    ProductAdminForm,
    ProductAttributeAdminForm,
)
from catalog.models import Product, ProductAttribute, ProductCategory, Size


def _jpeg(name="cat.jpg"):
    buf = BytesIO()
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


class ProductAdminFormTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(title="Килими")

    def _base(self, **overrides):
        data = {
            "title": "Килим тест",
            "ar_status": "none",
            "is_new": True,
            "categories": [self.category.pk],
        }
        data.update(overrides)
        return data

    def test_title_required(self):
        form = ProductAdminForm(
            data=self._base(title="   "),
            files={"image": _jpeg()},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_image_required_on_add(self):
        form = ProductAdminForm(data=self._base())
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_rejects_default_image_path(self):
        # Model default sneaks into cleaned_data as path string on add
        form = ProductAdminForm(data=self._base())
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
        self.assertNotIn(DEFAULT_CATALOG_IMAGE, form.cleaned_data.values())

    def test_keeps_existing_real_image_on_change(self):
        product = Product.admin_objects.create(title="Existing")
        product.image.save("real.jpg", _jpeg("real.jpg"), save=True)
        form = ProductAdminForm(
            data=self._base(title="Existing"),
            instance=product,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_category_required(self):
        form = ProductAdminForm(
            data=self._base(categories=[]),
            files={"image": _jpeg()},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("categories", form.errors)

    def test_ok_with_image_and_category(self):
        form = ProductAdminForm(
            data=self._base(),
            files={"image": _jpeg()},
        )
        self.assertTrue(form.is_valid(), form.errors)


class ProductAttributeAdminFormTests(TestCase):
    def setUp(self):
        self.size = Size.objects.create(title="100x150")
        self.product = Product.admin_objects.create(title="P")

    def _form(self, data):
        return ProductAttributeAdminForm(
            data=data,
            instance=ProductAttribute(product=self.product),
        )

    def test_fixed_requires_size_price_quantity(self):
        form = self._form(
            {
                "size": self.size.pk,
                "price": "",
                "quantity": "",
                "custom_attribute": False,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)
        self.assertIn("quantity", form.errors)

    def test_fixed_ok(self):
        form = self._form(
            {
                "size": self.size.pk,
                "price": "1500",
                "quantity": "3",
                "custom_attribute": False,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_custom_requires_custom_price(self):
        form = self._form(
            {
                "custom_attribute": True,
                "quantity": "1",
                "custom_price": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("custom_price", form.errors)

    def test_empty_extra_row_ok(self):
        # Extra inline rows: formset sets empty_permitted + use_required_attribute=False
        form = ProductAttributeAdminForm(
            data={},
            empty_permitted=True,
            use_required_attribute=False,
        )
        self.assertTrue(form.is_valid(), form.errors)
