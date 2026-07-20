"""Tests: on-screen copy and montage helpers for the guess-the-price format."""

import unittest

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from catalog.models import Product, ProductAttribute, ProductImage, Size
from social.models import TikTokDailyPick
from social.services import tiktok_montage as montage
from social.services.tiktok_script import (
    CTA,
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

    def test_hook_rotates_but_the_closing_line_does_not(self):
        product = _product()
        pick = TikTokDailyPick.objects.create(product=product)
        script = build_script(pick)
        self.assertEqual(script["cta"], CTA)
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


class AnimationExpressionTests(TestCase):
    """The filtergraph is assembled as text; a stray comma silently breaks it."""

    def test_fade_escapes_commas_for_the_filtergraph(self):
        expr = montage._fade_in(0.2)
        self.assertIn(r"\,", expr)
        self.assertNotIn(", ", expr)
        self.assertTrue(expr.startswith("alpha='") and expr.endswith("'"))

    def test_fade_in_out_covers_up_hold_and_down(self):
        expr = montage._fade_in_out(1.0, 1.0)
        self.assertIn("1.00", expr)
        self.assertIn("2.00", expr)

    def test_drift_moves_towards_the_base_position(self):
        """Motion comes from y, not fontsize: animated sizes segfault ffmpeg."""
        expr = montage._drift_y("h*0.5", 0.3, rise=20)
        self.assertIn("h*0.5", expr)
        self.assertIn("20*", expr)
        self.assertTrue(expr.startswith("y='"))

    def test_caption_lines_do_not_overlap(self):
        """Plates stack with a gap; below LINE_STEP they darken at the seam."""
        self.assertGreaterEqual(montage.LINE_STEP, 1.6)

    def test_animated_caption_emits_alpha_and_y_per_line(self):
        out = montage._caption(
            "Скільки б ви дали за такий килим 1.2 × 2.0 м?",
            y_frac=0.16, size=56, font="/f.ttf", wrap=26, appear_at=0.2,
        )
        self.assertEqual(out.count("alpha='"), 2)
        self.assertEqual(out.count("y='"), 2)

    def test_static_caption_uses_a_plain_y(self):
        out = montage._caption("Ціна", y_frac=0.7, size=90, font="/f.ttf")
        self.assertIn("y=h*0.7", out)
        self.assertNotIn("alpha='", out)


class MusicLibraryTests(TestCase):
    def test_pick_track_is_deterministic(self):
        from unittest.mock import patch

        from social.services import tiktok_music

        tracks = [f"{tiktok_music.MUSIC_DIR}/track-{i:02d}.wav" for i in (1, 2, 3)]
        with patch.object(tiktok_music, "library_paths", return_value=tracks):
            self.assertEqual(tiktok_music.pick_track(7), tiktok_music.pick_track(7))

    def test_empty_library_degrades_to_silence(self):
        """A missing library must not fail the night's run."""
        from unittest.mock import patch

        from social.services import tiktok_music

        with patch.object(tiktok_music, "library_paths", return_value=[]):
            self.assertEqual(tiktok_music.pick_track(1), "")
