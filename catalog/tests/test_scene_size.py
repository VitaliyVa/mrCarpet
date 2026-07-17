from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from catalog.models import Product, ProductAttribute, Size
from catalog.services.replicate_prompt_options import ScenePromptOptions
from catalog.services.replicate_prompts import build_scene_prompt
from catalog.services.scene_size import (
    SceneSizeError,
    get_first_product_size_label,
    resolve_scene_size,
)


User = get_user_model()


def _make_product(title="Test rug"):
    return Product.admin_objects.create(title=title)


def _jpeg_upload(name="source.jpg"):
    buf = BytesIO()
    Image.new("RGB", (64, 64), color=(120, 80, 40)).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


class SceneSizeResolveTests(TestCase):
    def test_first_size_by_pk_order(self):
        product = _make_product()
        small = Size.objects.create(title="Ø 67 см")
        large = Size.objects.create(title="2.4x3.4")
        ProductAttribute.objects.create(
            product=product, size=large, quantity=1, price=1000
        )
        ProductAttribute.objects.create(
            product=product, size=small, quantity=1, price=500
        )
        # First by pk is large (created first)
        self.assertEqual(get_first_product_size_label(product), "2.4x3.4")

    def test_skips_empty_size(self):
        product = _make_product()
        ProductAttribute.objects.create(
            product=product, size=None, quantity=1, price=100, custom_attribute=True
        )
        sized = Size.objects.create(title="1.5x2.3")
        ProductAttribute.objects.create(
            product=product, size=sized, quantity=1, price=800
        )
        self.assertEqual(get_first_product_size_label(product), "1.5x2.3")

    def test_resolve_from_db(self):
        product = _make_product()
        size = Size.objects.create(title="Ø 67 см")
        ProductAttribute.objects.create(
            product=product, size=size, quantity=2, price=900
        )
        info = resolve_scene_size(product_id=product.pk)
        self.assertEqual(info.label, "Ø 67 см")
        self.assertEqual(info.width_m, Decimal("0.67"))
        self.assertEqual(info.length_m, Decimal("0.67"))
        self.assertEqual(info.source, "db")

    def test_resolve_fallback_request_label(self):
        info = resolve_scene_size(size_label="1.2x2.5")
        self.assertEqual(info.label, "1.2x2.5")
        self.assertEqual(info.width_m, Decimal("1.2"))
        self.assertEqual(info.length_m, Decimal("2.5"))
        self.assertEqual(info.source, "request")

    def test_resolve_missing_raises(self):
        product = _make_product()
        with self.assertRaises(SceneSizeError):
            resolve_scene_size(product_id=product.pk)

    def test_db_wins_over_request_label(self):
        product = _make_product()
        size = Size.objects.create(title="0.6x1.0")
        ProductAttribute.objects.create(
            product=product, size=size, quantity=1, price=400
        )
        info = resolve_scene_size(product_id=product.pk, size_label="9.9x9.9")
        self.assertEqual(info.label, "0.6x1.0")
        self.assertEqual(info.source, "db")


class ScenePromptSizeTests(TestCase):
    def test_prompt_includes_round_size(self):
        opts = ScenePromptOptions(
            size_label="Ø 67 см",
            width_m="0.67",
            length_m="0.67",
        )
        prompt = build_scene_prompt(opts)
        self.assertIn("Ø 67 см", prompt)
        self.assertIn("0.67", prompt)
        self.assertIn("ROUND rug", prompt)
        self.assertIn("SCALE (CRITICAL", prompt)

    def test_prompt_includes_rectangular_size(self):
        opts = ScenePromptOptions(
            size_label="2.4x3.4",
            width_m="2.4",
            length_m="3.4",
        )
        prompt = build_scene_prompt(opts)
        self.assertIn("2.4x3.4", prompt)
        self.assertIn("2.4 m × 3.4 m", prompt)

    def test_prompt_requires_size(self):
        with self.assertRaises(ValueError):
            build_scene_prompt(ScenePromptOptions())


class SceneGenerateAdminGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            email="admin@example.com",
            password="test-pass-123",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("admin:catalog_product_generate_images")

    def test_scene_without_size_returns_400(self):
        product = _make_product()
        response = self.client.post(
            self.url,
            {
                "phase": "scene",
                "product_id": str(product.pk),
                "source_image": _jpeg_upload(),
            },
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("розмір", data["error"].lower())

    @patch("catalog.admin.ReplicateProductImageService")
    def test_scene_with_db_size_injects_into_options(self, service_cls):
        product = _make_product()
        size = Size.objects.create(title="Ø 67 см")
        ProductAttribute.objects.create(
            product=product, size=size, quantity=1, price=700
        )

        service = service_cls.return_value
        service.generate_phase.return_value = (
            b"webp-bytes",
            {
                "logs": [],
                "prompt_options": {
                    "size_label": "Ø 67 см",
                    "width_m": "0.67",
                    "length_m": "0.67",
                },
            },
        )

        response = self.client.post(
            self.url,
            {
                "phase": "scene",
                "product_id": str(product.pk),
                "source_image": _jpeg_upload(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        args, kwargs = service.generate_phase.call_args
        self.assertEqual(args[1], "scene")
        gen_options = args[2]
        self.assertEqual(gen_options.scene.size_label, "Ø 67 см")
        self.assertEqual(gen_options.scene.width_m, "0.67")
        self.assertEqual(gen_options.scene.length_m, "0.67")
