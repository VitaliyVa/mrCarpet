"""Carousel slides (1080x1350 JPEG) announcing a blog article.

Slide 1   the article cover, a warm dark gradient and the hook in big white type.
Slides 2… one tip each on the shop's sand background, with a slide counter.
Last      up to three rugs with their current price and a call to action.

Every text block is fitted into a fixed box: the font shrinks step by step
until the wrapped lines fit, and only at the minimum size are lines cut with
an ellipsis. Nothing can run off the slide, whatever length the spec has.

Fonts: Futura PT from static/utils/fonts (the site's own typeface, ParaType
license), falling back to Inter from project/fonts (SIL OFL), then to
Pillow's default so rendering never fails on a box without them.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

W, H = 1080, 1350
SAND = (246, 241, 234)
SAND_DARK = (236, 226, 213)
BROWN = (164, 108, 70)
INK = (47, 42, 38)
INK_SOFT = (110, 98, 88)
WHITE = (255, 255, 255)
MARGIN = 84
JPEG_QUALITY = 90

MARK = "mr.Carpet"
CTA = "Більше порад і ці килими: посилання в профілі"
MAX_TIPS = 4
MAX_PRODUCTS = 3

_FONT_FILES = {
    "bold": ("static/utils/fonts/FuturaPT-Bold.ttf", "project/fonts/Inter-Bold.ttf"),
    "medium": ("static/utils/fonts/FuturaPT-Medium.ttf", "project/fonts/Inter-SemiBold.ttf"),
    "book": ("static/utils/fonts/FuturaPT-Book.ttf", "project/fonts/Inter-Regular.ttf"),
}
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font_path(weight: str) -> str | None:
    base = Path(settings.BASE_DIR)
    for rel in _FONT_FILES[weight]:
        path = base / rel
        if path.exists():
            return str(path)
    return None


def font(weight: str, size: int):
    key = (weight, size)
    if key not in _font_cache:
        path = _font_path(weight)
        if path:
            _font_cache[key] = ImageFont.truetype(path, size)
        else:  # pragma: no cover - only on a box without any bundled font
            _font_cache[key] = ImageFont.load_default(size=size)
    return _font_cache[key]


def clean_text(text: str | None) -> str:
    """Normalise spacing and swap glyphs the fonts lack for ones they have."""
    text = (text or "").replace(" ", " ").replace(" ", " ")
    text = text.replace("\r", " ").replace("\n", " ")
    return " ".join(text.split(" ")).strip()


# --------------------------------------------------------------------------
# Text fitting
# --------------------------------------------------------------------------


@dataclass
class FittedText:
    font: object
    lines: list[str]
    line_height: int

    @property
    def height(self) -> int:
        return self.line_height * len(self.lines)


def _split_long_word(word: str, fnt, width: int) -> list[str]:
    parts, cur = [], ""
    for ch in word:
        if cur and fnt.getlength(cur + ch) > width:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


def wrap(text: str, fnt, width: int) -> list[str]:
    """Greedy word wrap by real glyph widths. Splits on plain spaces only, so
    a no-break space keeps «від 1 200 грн» on one line."""
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        if not word:
            continue
        pieces = [word] if fnt.getlength(word) <= width else _split_long_word(word, fnt, width)
        for piece in pieces:
            trial = f"{cur} {piece}" if cur else piece
            if fnt.getlength(trial) <= width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = piece
    if cur:
        lines.append(cur)
    return lines


def _ellipsize(line: str, fnt, width: int) -> str:
    line = line.rstrip(" .,;:")
    while line and fnt.getlength(line + "…") > width:
        line = line[:-1].rstrip(" .,;:")
    return line + "…"


def fit_text(
    text: str,
    weight: str,
    width: int,
    height: int,
    *,
    max_size: int,
    min_size: int,
    leading: float = 1.18,
    max_lines: int | None = None,
) -> FittedText:
    text = clean_text(text)
    size = max_size
    while True:
        fnt = font(weight, size)
        line_height = int(round(size * leading))
        lines = wrap(text, fnt, width)
        fits = line_height * len(lines) <= height and (
            max_lines is None or len(lines) <= max_lines
        )
        if fits or size <= min_size:
            break
        size = max(min_size, size - 2)
    allowed = max(1, height // line_height)
    if max_lines is not None:
        allowed = min(allowed, max_lines)
    if len(lines) > allowed:
        lines = lines[:allowed]
        lines[-1] = _ellipsize(lines[-1], fnt, width)
    return FittedText(font=fnt, lines=lines, line_height=line_height)


def fit_prefer_one_line(text, weight, width, height, *, max_size, one_line_min, min_size, leading=1.15):
    """One line if it fits at a readable size, else wrap: avoids a lonely last word."""
    single = fit_text(text, weight, width, height, max_size=max_size, min_size=one_line_min, leading=leading, max_lines=1)
    if not single.lines[-1].endswith("…"):
        return single
    return fit_text(text, weight, width, height, max_size=max_size, min_size=min_size, leading=leading)


def draw_text(draw, fitted: FittedText, x: int, y: int, fill, *, align="left", width=0) -> int:
    """Draw fitted lines from the top-left corner; returns the bottom y."""
    ascent_fix = int(fitted.line_height * 0.12)
    for i, line in enumerate(fitted.lines):
        lx = x
        if align == "center" and width:
            lx = x + (width - fitted.font.getlength(line)) / 2
        draw.text((lx, y + i * fitted.line_height - ascent_fix), line, font=fitted.font, fill=fill)
    return y + fitted.height


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------


def open_image(file_field) -> Image.Image | None:
    """A FieldFile (or path) as an RGB image, or None when it is unreadable."""
    if not file_field:
        return None
    try:
        if isinstance(file_field, (str, os.PathLike)):
            img = Image.open(file_field)
        else:
            name = getattr(file_field, "name", "") or ""
            if not name or not file_field.storage.exists(name):
                return None
            with file_field.storage.open(name, "rb") as fh:
                img = Image.open(io.BytesIO(fh.read()))
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")
    except Exception as exc:
        logger.warning("social card: cannot open image %s: %s", file_field, exc)
        return None


def cover_crop(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.45))


def _warm_gradient(size: tuple[int, int]) -> Image.Image:
    """Transparent at the top, warm near-black at the bottom (RGBA)."""
    w, h = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    px = ImageDraw.Draw(overlay)
    start = int(h * 0.28)
    for y in range(h):
        if y < start:
            alpha = 40
        else:
            t = (y - start) / max(1, h - start)
            alpha = int(40 + (232 - 40) * (t ** 1.15))
        px.line([(0, y), (w, y)], fill=(38, 24, 15, alpha))
    return overlay


def _mark(draw, x: int, y: int, fill, size: int = 34) -> None:
    draw.text((x, y), MARK, font=font("bold", size), fill=fill)


def _counter(draw, index: int, total: int, fill) -> None:
    text = f"{index}/{total}"
    fnt = font("medium", 32)
    draw.text((W - MARGIN - fnt.getlength(text), MARGIN - 4), text, font=fnt, fill=fill)


def _arrow(draw, x: int, y: int, length: int, fill, width: int = 4) -> None:
    draw.line([(x, y), (x + length, y)], fill=fill, width=width)
    draw.line([(x + length - 14, y - 12), (x + length, y)], fill=fill, width=width)
    draw.line([(x + length - 14, y + 12), (x + length, y)], fill=fill, width=width)


# --------------------------------------------------------------------------
# Slides
# --------------------------------------------------------------------------


def render_cover(hook: str, cover: Image.Image | None, total: int) -> Image.Image:
    if cover is not None:
        base = cover_crop(cover, (W, H)).convert("RGBA")
        base.alpha_composite(_warm_gradient((W, H)))
        canvas = base.convert("RGB")
        title_fill, mark_fill, hint_fill = WHITE, WHITE, SAND
    else:
        canvas = Image.new("RGB", (W, H), INK)
        title_fill, mark_fill, hint_fill = WHITE, SAND, SAND

    draw = ImageDraw.Draw(canvas)
    _mark(draw, MARGIN, MARGIN - 6, mark_fill)
    _counter(draw, 1, total, mark_fill)

    box_w = W - 2 * MARGIN
    box_h = 520
    fitted = fit_text(hook, "bold", box_w, box_h, max_size=104, min_size=54, leading=1.08)
    hint_y = H - MARGIN - 36
    top = hint_y - 56 - fitted.height
    draw.rectangle([MARGIN, top - 44, MARGIN + 96, top - 36], fill=BROWN)
    draw_text(draw, fitted, MARGIN, top, title_fill)

    hint_font = font("medium", 34)
    draw.text((MARGIN, hint_y - 4), "Гортайте", font=hint_font, fill=hint_fill)
    _arrow(draw, MARGIN + int(hint_font.getlength("Гортайте")) + 20, hint_y + 18, 56, hint_fill)
    return canvas


def render_tip(index: int, total: int, number: int, title: str, text: str) -> Image.Image:
    canvas = Image.new("RGB", (W, H), SAND)
    draw = ImageDraw.Draw(canvas)
    _mark(draw, MARGIN, MARGIN - 6, BROWN)
    _counter(draw, index, total, INK_SOFT)

    box_w = W - 2 * MARGIN
    area_top, area_bottom = 220, H - 130
    label_h, label_gap, rule_gap, body_gap = 44, 40, 44, 52

    head = fit_text(title, "bold", box_w, 400, max_size=84, min_size=46, leading=1.1)
    fixed = label_h + label_gap + head.height + rule_gap + 6 + body_gap
    body = fit_text(
        text, "book", box_w, max(area_bottom - area_top - fixed, 60),
        max_size=50, min_size=32, leading=1.3,
    )
    block_h = fixed + body.height
    # Short tips sit in the optical centre instead of hugging the top.
    y = area_top + max(0, (area_bottom - area_top - block_h) // 2 - 30)

    # Number badge + label.
    badge = 44
    draw.ellipse([MARGIN, y, MARGIN + badge, y + badge], fill=BROWN)
    num_font = font("bold", 28)
    num = str(number)
    draw.text(
        (MARGIN + (badge - num_font.getlength(num)) / 2, y + 4),
        num, font=num_font, fill=WHITE,
    )
    draw.text((MARGIN + badge + 18, y + 2), "Порада", font=font("medium", 36), fill=BROWN)
    y += label_h + label_gap

    y = draw_text(draw, head, MARGIN, y, INK)
    y += rule_gap
    draw.rectangle([MARGIN, y, MARGIN + 120, y + 6], fill=BROWN)
    y += 6 + body_gap
    draw_text(draw, body, MARGIN, y, INK)

    draw.rectangle([0, H - 18, W, H], fill=BROWN)
    return canvas


@dataclass
class ProductTile:
    title: str
    price_line: str
    image: Image.Image | None = None


def render_products(index: int, total: int, tiles: list[ProductTile], heading: str = "Килими до поради") -> Image.Image:
    canvas = Image.new("RGB", (W, H), SAND)
    draw = ImageDraw.Draw(canvas)
    _mark(draw, MARGIN, MARGIN - 6, BROWN)
    _counter(draw, index, total, INK_SOFT)

    box_w = W - 2 * MARGIN
    head = fit_text(heading, "bold", box_w, 150, max_size=76, min_size=48, leading=1.08, max_lines=2)
    head_bottom = draw_text(draw, head, MARGIN, 190, INK)

    tiles = tiles[:MAX_PRODUCTS]
    n = max(1, len(tiles))
    gap = 28
    col_w = (W - 2 * 60 - gap * (n - 1)) // n
    photo_h = min(int(col_w * 1.35), 560)
    band_h = 170
    band_top = H - MARGIN - band_h + 20
    group_h = photo_h + 22 + 2 * 38 + 16 + 46
    top = head_bottom + max(50, (band_top - head_bottom - group_h) // 2)
    for i, tile in enumerate(tiles):
        x = 60 + i * (col_w + gap)
        draw.rounded_rectangle([x, top, x + col_w, top + photo_h], radius=22, fill=SAND_DARK)
        if tile.image is not None:
            photo = cover_crop(tile.image, (col_w, photo_h))
            mask = Image.new("L", (col_w, photo_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, col_w, photo_h], radius=22, fill=255)
            canvas.paste(photo, (x, top), mask)
        name_top = top + photo_h + 22
        name = fit_text(tile.title, "medium", col_w, 2 * 38, max_size=32, min_size=24, leading=1.15, max_lines=2)
        draw_text(draw, name, x, name_top, INK)
        # Prices on one baseline whatever the title length.
        price = fit_text(tile.price_line, "bold", col_w, 52, max_size=42, min_size=26, leading=1.1, max_lines=1)
        draw_text(draw, price, x, name_top + 2 * 38 + 16, BROWN)

    # Call to action band.
    draw.rounded_rectangle([MARGIN - 20, band_top, W - MARGIN + 20, band_top + band_h], radius=28, fill=BROWN)
    cta = fit_prefer_one_line(CTA, "bold", box_w - 40, band_h - 50, max_size=46, one_line_min=34, min_size=28)
    draw_text(draw, cta, MARGIN, band_top + (band_h - cta.height) // 2 + 4, WHITE, align="center", width=box_w)
    return canvas


# --------------------------------------------------------------------------
# Article → slides
# --------------------------------------------------------------------------


@dataclass
class CardSpec:
    hook: str
    tips: list[dict] = field(default_factory=list)
    products: list[str] = field(default_factory=list)


def product_tiles(slugs: list[str]) -> list[ProductTile]:
    """Current price via build_card, the same rule the article cards use."""
    if not slugs:
        return []
    from blog.services.product_cards import build_card
    from catalog.models import Product

    found = {
        p.slug: p
        for p in Product.objects.filter(slug__in=slugs).prefetch_related("product_attr")
    }
    tiles = []
    for slug in slugs:
        product = found.get(slug)
        card = build_card(product) if product else None
        if not card:
            continue
        price = f"{card['price']} {card['unit']}"
        if card.get("from_label"):
            price = f"від {price}"
        tiles.append(ProductTile(title=card["title"] or "", price_line=price, image=open_image(product.image)))
    # A rug without a photo does not sell in a feed: drop those while any
    # tile has one.
    with_photo = [t for t in tiles if t.image is not None]
    return (with_photo or tiles)[:MAX_PRODUCTS]


def article_product_slugs(article) -> list[str]:
    from blog.services.product_cards import ANY_PRODUCTS_RE, parse_slugs

    slugs: list[str] = []
    for m in ANY_PRODUCTS_RE.finditer(getattr(article, "description", "") or ""):
        for slug in parse_slugs(m.group(1)):
            if slug not in slugs:
                slugs.append(slug)
    return slugs


def render_article_slides(article, spec: CardSpec) -> list[Image.Image]:
    tips = [t for t in (spec.tips or []) if (t.get("title") or t.get("text"))][:MAX_TIPS]
    tiles = product_tiles(spec.products or article_product_slugs(article))
    total = 1 + len(tips) + (1 if tiles else 0)

    slides = [render_cover(spec.hook or article.title or "", open_image(article.image), total)]
    for i, tip in enumerate(tips, start=1):
        slides.append(render_tip(i + 1, total, i, tip.get("title") or "", tip.get("text") or ""))
    if tiles:
        slides.append(render_products(total, total, tiles))
    return slides


def slide_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buf.getvalue()


def save_slides_to_dir(slides: list[Image.Image], folder: str | os.PathLike) -> list[str]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, img in enumerate(slides, start=1):
        path = folder / f"{i:02d}.jpg"
        path.write_bytes(slide_bytes(img))
        paths.append(str(path.resolve()))
    return paths


def storage_dir(article, tag: str = "") -> str:
    """media-relative folder: social/article_cards/<slug>/[<tag>/]"""
    slug = (article.slug or f"article-{article.pk}").strip("/")
    parts = ["social", "article_cards", slug]
    if tag:
        parts.append(tag)
    return "/".join(parts)


def save_slides_to_storage(slides: list[Image.Image], folder: str) -> list[str]:
    """Write slides into default_storage under `folder`, replacing old files
    of the same name. Returns storage names (for ImageField.name)."""
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    names = []
    for i, img in enumerate(slides, start=1):
        name = f"{folder}/{i:02d}.jpg"
        if default_storage.exists(name):
            default_storage.delete(name)
        names.append(default_storage.save(name, ContentFile(slide_bytes(img))))
    return names
