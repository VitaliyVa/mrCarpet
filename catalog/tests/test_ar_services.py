from decimal import Decimal
from io import BytesIO

from django.test import SimpleTestCase
from PIL import Image

from catalog.services.make_glb import build_carpet_glb, detect_image
from catalog.services.parse_size import SizeParseError, normalize_size_key, parse_size_label


class ParseSizeLabelTests(SimpleTestCase):
    def test_latin_x(self):
        self.assertEqual(parse_size_label("1.0x2.0"), (Decimal("1.0"), Decimal("2.0")))

    def test_cyrillic_x(self):
        self.assertEqual(parse_size_label("2.0х4.0"), (Decimal("2.0"), Decimal("4.0")))

    def test_multiply_sign_and_comma(self):
        self.assertEqual(parse_size_label("1,5×2"), (Decimal("1.5"), Decimal("2")))

    def test_spaces_and_unit(self):
        self.assertEqual(parse_size_label("1.0 x 2.0 м"), (Decimal("1.0"), Decimal("2.0")))

    def test_invalid(self):
        with self.assertRaises(SizeParseError):
            parse_size_label("huge")

    def test_normalize_key(self):
        self.assertEqual(normalize_size_key("1", "2"), "1.00x2.00")


class MakeGlbTests(SimpleTestCase):
    def _jpeg_bytes(self):
        buf = BytesIO()
        Image.new("RGB", (8, 16), (120, 80, 40)).save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def _png_rgba_bytes(self):
        buf = BytesIO()
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for x in range(4, 12):
            for y in range(4, 12):
                img.putpixel((x, y), (180, 60, 40, 255))
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_jpeg_plane(self):
        jpeg = self._jpeg_bytes()
        mime, has_alpha = detect_image(jpeg)
        self.assertEqual(mime, "image/jpeg")
        self.assertFalse(has_alpha)
        glb = build_carpet_glb(jpeg, 1.0, 2.0)
        self.assertTrue(glb.startswith(b"glTF"))
        self.assertGreater(len(glb), 100)

    def test_png_alpha_blend(self):
        png = self._png_rgba_bytes()
        mime, has_alpha = detect_image(png)
        self.assertEqual(mime, "image/png")
        self.assertTrue(has_alpha)
        glb = build_carpet_glb(png, 1.4, 1.4, alpha_mode="auto")
        self.assertIn(b"BLEND", glb)
