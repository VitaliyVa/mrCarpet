from django.test import SimpleTestCase, TestCase

from catalog.models import Product, ProductAttribute, Size
from catalog.services.seo_generate import (
    _extract_json_object,
    build_user_prompt,
    collect_product_context,
    parse_seo_payload,
)


class SeoGenerateParseTests(SimpleTestCase):
    def test_extract_json_from_fence(self):
        text = '```json\n{"meta_title":"A","meta_description":"B","meta_keys":"","description":"C"}\n```'
        data = _extract_json_object(text)
        self.assertEqual(data["meta_title"], "A")

    def test_parse_strips_brand_suffix(self):
        fields = parse_seo_payload(
            {
                "meta_title": "Круглий килим | mr.Carpet",
                "meta_description": "x" * 20,
                "meta_keys": "килим, круглий",
                "description": "Короткий опис.",
            },
            fill_description=True,
        )
        self.assertEqual(fields["meta_title"], "Круглий килим")


class SeoGenerateContextTests(TestCase):
    def test_collect_context_includes_primary_size(self):
        product = Product.admin_objects.create(title="Test rug", description="")
        size = Size.objects.create(title="1.6х2.3")
        ProductAttribute.objects.create(
            product=product,
            size=size,
            quantity=1,
            price=1000,
        )
        ctx = collect_product_context(product)
        self.assertEqual(ctx["primary_size"], "1.6х2.3")
        self.assertTrue(ctx["need_description"])
        self.assertEqual(ctx["sizes"][0]["size"], "1.6х2.3")
        prompt = build_user_prompt(ctx)
        self.assertIn("PRODUCT DATA", prompt)
        self.assertIn("ПОРОЖНЄ", prompt)
