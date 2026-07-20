"""Tests: on-screen copy and montage helpers for the guess-the-price format."""

import unittest

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from catalog.models import Product, ProductAttribute, ProductImage, Size
from social.models import TikTokDailyPick
from social.services import tiktok_montage as montage
from social.services.tiktok_script import (
    CTAS,
    HOOKS,
    build_script,
    first_priced_attribute,
    format_price,
    normalise_size,
)

PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
)


def _product(title="Килим", size_label="1.2x2.0", price=2300):
    product = Product.objects.create(title=title, slug=title.lower())
    ProductImage.objects.create(
        product=product,
        image=SimpleUploadedFile("s.gif", PIXEL, content_type="image/gif"),
        is_ai=True,
    )
    if size_label:
        size = Size.objects.create(title=size_label)
        ProductAttribute.objects.create(
            product=product, size=size, price=price, quantity=1
        )
    return product


class SizeFormattingTests(TestCase):
    def test_cyrillic_separator(self):
        self.assertEqual(normalise_size("0.8х1.5"), "0.8 × 1.5 м")

    def test_latin_separator(self):
        """The catalogue mixes both 'х' and 'x' — output must not."""
        self.assertEqual(normalise_size("0.5x0.8"), "0.5 × 0.8 м")

    def test_comma_decimals(self):
        self.assertEqual(normalise_size("1,2х2,0"), "1.2 × 2.0 м")

    def test_unparseable_label_passes_through(self):
        self.assertEqual(normalise_size("кругла"), "кругла")

    def test_empty(self):
        self.assertEqual(normalise_size(""), "")


class PriceFormattingTests(TestCase):
    def test_hundreds(self):
        self.assertEqual(format_price(475), "475 ₴")

    def test_thousands_get_a_space(self):
        self.assertEqual(format_price(2300), "2 300 ₴")

    def test_none(self):
        self.assertEqual(format_price(None), "")


class ScriptTests(TestCase):
    def test_hook_names_the_size_that_is_priced(self):
        """The guess must be anchored to the variant whose price is revealed."""
        product = _product(size_label="1.2x2.0", price=2300)
        pick = TikTokDailyPick.objects.create(product=product)
        script = build_script(pick)
        self.assertIn("1.2 × 2.0 м", script["hook"])
        self.assertEqual(script["price"], "2 300 ₴")

    def test_variants_come_from_the_configured_pools(self):
        product = _product()
        pick = TikTokDailyPick.objects.create(product=product)
        script = build_script(pick)
        self.assertTrue(any(script["cta"] == c for c in CTAS))
        self.assertEqual(len(HOOKS), 5)

    def test_script_is_deterministic_for_a_pick(self):
        """Regenerating a video must not silently change the copy."""
        product = _product()
        pick = TikTokDailyPick.objects.create(product=product)
        self.assertEqual(build_script(pick), build_script(pick))

    def test_product_without_price_is_rejected(self):
        product = _product(size_label="")
        pick = TikTokDailyPick.objects.create(product=product)
        with self.assertRaises(ValueError):
            build_script(pick)

    def test_pick_without_product_is_rejected(self):
        pick = TikTokDailyPick.objects.create(product=None)
        with self.assertRaises(ValueError):
            build_script(pick)

    def test_first_priced_attribute_skips_unpriced(self):
        product = _product(size_label="0.6x1.1", price=350)
        size = Size.objects.create(title="2.0x3.0")
        ProductAttribute.objects.create(
            product=product, size=size, price=None, quantity=1
        )
        self.assertEqual(first_priced_attribute(product).price, 350)


class MontageHelperTests(TestCase):
    def test_wrap_breaks_on_words(self):
        lines = montage._wrap("Скільки б ви дали за такий килим 1.2 × 2.0 м?", 26)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(line) <= 30 for line in lines))

    def test_emoji_stripped_before_drawing(self):
        """DejaVu has no emoji glyphs — they would render as empty boxes."""
        self.assertEqual(montage._strip_emoji("Хто вгадав — пишіть 👇"), "Хто вгадав — пишіть")

    def test_cyrillic_survives_stripping(self):
        self.assertEqual(montage._strip_emoji("Вгадали? Пишіть"), "Вгадали? Пишіть")

    def test_colons_escaped_for_filtergraph(self):
        self.assertEqual(montage._esc("a:b"), r"a\:b")

    def test_windows_drive_letter_escaped_in_font_path(self):
        """An unescaped drive letter breaks the whole filterchain."""
        self.assertEqual(
            montage._esc_path("C:/Windows/Fonts/arial.ttf"),
            r"C\:/Windows/Fonts/arial.ttf",
        )

    def test_backslashes_normalised(self):
        self.assertEqual(
            montage._esc_path(r"C:\fonts\a.ttf"), r"C\:/fonts/a.ttf"
        )


@unittest.skipUnless(montage.ffmpeg_available(), "ffmpeg not installed")
class MontageRenderTests(TestCase):
    def test_font_lookup_finds_something(self):
        self.assertTrue(montage.font_path())
