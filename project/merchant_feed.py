"""Google Merchant Center product feed (RSS 2.0 + g: namespace).

One feed item per sellable size (ProductAttribute). Sizes of one product share
`item_group_id`, so Google shows them as variants of one listing. Meta's
catalog reads the same URL.

Facts only from the DB, nothing generated:
- brand is always mr.Carpet (own-label decision), no GTIN (`identifier_exists=no`);
- no `mpn`: with `identifier_exists=no` an MPN contradicts the flag, and our
  pk is not a manufacturer part number;
- id is stable `<product.pk>-<attr.pk>`; `link` carries `?size=<attr.pk>` so
  the PDP opens with that size and its price already rendered (canonical
  stays the clean product URL);
- color / shape / type words are parsed from the shop-written title (and
  active_color / specs as fallback); material, pattern and `product_detail`
  come from ProductSpecification rows (same rows as the PDP `<dl>` and the
  JSON-LD `additionalProperty`);
- product_length / product_width come from the size label.
Custom-size attributes (price per m², no fixed price) are skipped.
"""

from __future__ import annotations

import html
import re
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils.html import strip_tags

from project.seo_jsonld import ORG_NAME, _google_product_category, _product_color
from project.seo_urls import absolute_site_url
from project.text_encoding import fix_utf8_mojibake

MAX_ADDITIONAL_IMAGES = 10
MAX_TITLE = 150
MAX_DESCRIPTION = 5000
SIZE_PARAM = "size"
DETAIL_SECTION = "Характеристики"

_SIZE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[xхXХ×]\s*(\d+(?:[.,]\d+)?)\s*$")
_CM_SIZE_RE = re.compile(r"^(\d+)x(\d+) см$")
_DIAMETER_RE = re.compile(r"^\s*(?:∅|Ø|ø|d|D)\s*(\d+(?:[.,]\d+)?)\s*(см|м)?\s*$")


def format_size(raw: str | None) -> str:
    """'1.2х2.0' (metres, Cyrillic x) -> '120x200 см'. Unknown formats pass through."""
    value = (raw or "").strip()
    match = _SIZE_RE.match(value)
    if not match:
        return value
    width, length = (float(g.replace(",", ".")) for g in match.groups())
    if width < 10 and length < 10:  # metres
        width, length = width * 100, length * 100
    return f"{round(width)}x{round(length)} см"


def size_dimensions(size: str) -> tuple[int, int] | None:
    """Formatted size -> (width_cm, length_cm); round '∅ 67 см' -> (67, 67)."""
    match = _CM_SIZE_RE.match(size or "")
    if match:
        return int(match.group(1)), int(match.group(2))
    match = _DIAMETER_RE.match(size or "")
    if match:
        value = float(match.group(1).replace(",", "."))
        if match.group(2) == "м" or value < 10:
            value *= 100
        return round(value), round(value)
    return None


def _money(value) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))} UAH"


def _clean(value: str | None) -> str:
    """Strip HTML + entities, fix mojibake, collapse spaces (newlines kept)."""
    text = html.unescape(strip_tags(fix_utf8_mojibake(value or "")))
    lines = (re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _text(value: str | None, limit: int) -> str:
    return _clean(value)[:limit].strip()


def product_description(product, limit: int = MAX_DESCRIPTION) -> str:
    """Full product description when it says more than the meta one, else meta."""
    full = _clean(product.description)
    meta = _clean(product.meta_description)
    text = full if len(full) > len(meta) else meta
    return (text or _clean(product.title))[:limit].strip()


def product_specs(product) -> list[tuple[str, str]]:
    """(name, value) rows, same source and filter as the PDP specs `<dl>`."""
    rows = []
    for row in product.product_specs.all():
        if not row.specification or not row.spec_value:
            continue
        name = _clean(row.specification.title)
        value = _clean(row.spec_value.title)
        if name and value:
            rows.append((name, value))
    return rows


def _spec(specs: list[tuple[str, str]], *keys: str) -> str:
    for name, value in specs:
        name_l = name.lower()
        if any(k in name_l for k in keys):
            return value
    return ""


# --- title parsing ----------------------------------------------------------

_NOUNS = {"килим", "килимок", "доріжка", "килимова"}
_PREPOSITIONS = {"для", "під", "в", "у", "на", "до"}
_SHAPES = (  # title word prefix -> (title adjective, spec-style noun)
    ("напівкол", "напівкруглий", "Напівколо"),
    ("напівкругл", "напівкруглий", "Напівколо"),
    ("овальн", "овальний", "Овал"),
    ("прямокутн", "прямокутний", "Прямокутник"),
    ("квадратн", "квадратний", "Квадрат"),
    ("кругл", "круглий", "Круг"),
)
_SPEC_SHAPE_TO_ADJ = {
    "овал": "овальний",
    "прямокутник": "прямокутний",
    "круг": "круглий",
    "коло": "круглий",
    "напівколо": "напівкруглий",
    "напівкруг": "напівкруглий",
    "квадрат": "квадратний",
}
_COLOR_STEMS = (
    "сір", "бежев", "коричнев", "чорн", "біл", "син", "блакитн", "голуб",
    "зелен", "жовт", "червон", "рожев", "фіолетов", "лілов", "бузков",
    "кремов", "молочн", "золот", "срібн", "помаранчев", "оранжев", "бордов",
    "теракотов", "оливков", "м'ятн", "мʼятн", "м’ятн", "бірюзов", "пісочн",
    "шоколадн", "вишнев", "персиков", "кавов", "пудров", "смарагдов",
    "гірчичн", "графітов", "антрацитов", "різнокольоров", "кольоров",
    "димчаст", "лаймов", "сливов", "норков", "океанічн", "темн", "коричев",
    "салатов", "лососев", "горіхов", "медов", "карамельн", "індиго",
)
_COLOR_NOUNS = {"графіт", "антрацит", "беж", "капучино", "мокко", "мультиколор", "крем"}
_COLOR_PREFIXES = ("темно", "світло", "яскраво", "ніжно", "насичено", "блідо")
_ADJ_ENDINGS = ("ий", "ій", "а", "я", "е", "є", "і", "ого", "их")
# 'фіолетово' in 'фіолетово-ліловий' / 'фіолетово білий'
_COMPOUND_ENDINGS = ("о",)
_DROP_PHRASES = (("без", "назви"),)  # admin placeholder, not a model name
_LOWER_CONNECTORS = {"з", "зі", "та", "і", "й", "and", "&"}
_CYRILLIC = re.compile(r"[а-яіїєґʼ’']", re.I)


def _color_part(part: str, last: bool) -> bool:
    if part in _COLOR_NOUNS or (not last and part in _COLOR_PREFIXES):
        return True
    for prefix in _COLOR_PREFIXES:
        if part.startswith(prefix) and len(part) > len(prefix):
            part = part[len(prefix):]
            break
    endings = _ADJ_ENDINGS if last else _ADJ_ENDINGS + _COMPOUND_ENDINGS
    return part in _COLOR_NOUNS or (
        part.startswith(_COLOR_STEMS) and part.endswith(endings)
    )


def _color_parts(word: str, last: bool = True) -> bool:
    lower = word.lower().strip(",.;")
    if not lower or not _CYRILLIC.search(lower):
        return False
    parts = [p for p in lower.split("-") if p]
    return bool(parts) and all(
        _color_part(p, last and n == len(parts) - 1) for n, p in enumerate(parts)
    )


def is_color_word(word: str) -> bool:
    return _color_parts(word, last=True)


_SHAPE_NOUNS = {"овал": "Овал", "круг": "Круг", "коло": "Круг", "прямокутник": "Прямокутник"}


def _shape_of(word: str) -> tuple[str, str] | None:
    lower = word.lower()
    if lower in _SHAPE_NOUNS:
        return _SPEC_SHAPE_TO_ADJ[lower], _SHAPE_NOUNS[lower]
    for prefix, adjective, noun in _SHAPES:
        if lower.startswith(prefix):
            return adjective, noun
    return None


_LATIN_LOWER = re.compile(r"[a-z]")


def _capitalize_model_word(word: str) -> str:
    """'isadora' -> 'Isadora'. Latin only: lowercase Cyrillic leftovers are
    themes ('місто', 'пазли'), not brand names, and stay as written."""
    if word.lower() in _LOWER_CONNECTORS or not _LATIN_LOWER.match(word[:1]):
        return word
    return word[:1].upper() + word[1:]


def parse_title(title: str) -> dict:
    """Split a shop title like 'Килим фіолетово-ліловий для ванни isadora' into
    noun / shape / descriptors / model / colors. Pure parsing — no new words."""
    words = _clean(title).replace("\n", " ").split()
    parsed = {"noun": "", "shape": "", "shape_noun": "", "type": [], "model": [], "colors": []}
    if not words or words[0].lower() not in _NOUNS:
        parsed["model"] = words
        return parsed
    parsed["noun"] = words[0][:1].upper() + words[0][1:]
    i = 1
    while i < len(words):
        word = words[i]
        lower = word.lower()
        is_cyr = bool(_CYRILLIC.search(lower))
        nxt = words[i + 1] if i + 1 < len(words) else ""
        shape = _shape_of(word) if is_cyr else None
        if tuple(w.lower() for w in words[i : i + 2]) in _DROP_PHRASES:
            i += 1
        elif shape and not parsed["shape"]:
            parsed["shape"], parsed["shape_noun"] = shape
        elif is_color_word(word):
            parsed["colors"].append(lower)
        elif nxt and _color_parts(word, last=False) and is_color_word(nxt):
            parsed["colors"].append(f"{lower}-{nxt.lower()}")  # 'фіолетово білий'
            i += 1
        elif (
            lower in _PREPOSITIONS
            and i + 1 < len(words)
            and _CYRILLIC.search(words[i + 1])
            and words[i + 1][:1].islower()
        ):
            parsed["type"] += [lower, words[i + 1]]
            i += 1
        elif is_cyr and word[:1].islower() and lower.endswith(_ADJ_ENDINGS[:2]):
            parsed["type"].append(word)  # other adjectives: 'турецький', 'пухнастий'
        else:
            parsed["model"].append(word)
        i += 1
    return parsed


def strip_title_colors(title: str) -> str:
    """The title without the colour words `parse_title` finds in it
    ('Килим овальний сірий Mira 24031' -> 'Килим овальний Mira 24031').
    Titles that do not start with a rug noun are returned unchanged."""
    words = _clean(title).split()
    if not words or words[0].lower() not in _NOUNS:
        return " ".join(words)
    kept = [words[0]]
    i = 1
    while i < len(words):
        word = words[i]
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if is_color_word(word):
            i += 1
        elif nxt and _color_parts(word, last=False) and is_color_word(nxt):
            i += 2  # 'фіолетово білий'
        else:
            kept.append(word)
            i += 1
    return " ".join(kept)


def feed_title(product, size: str, specs=None, color: str = "") -> str:
    """'Килим <тип> <Модель> <колір> <розмір>', ≤150 chars."""
    parsed = parse_title(product.title)
    if not parsed["noun"]:
        base = " ".join(parsed["model"])
        return _text(f"{base} {size}".strip(), MAX_TITLE)
    shape = parsed["shape"]
    if not shape:
        spec_shape = _spec(specs or [], "форма").lower()
        shape = _SPEC_SHAPE_TO_ADJ.get(spec_shape, "")
    colors = parsed["colors"]
    if not colors and color and all(is_color_word(w) for w in color.split()):
        colors = [color.lower()]
    model = [_capitalize_model_word(w) for w in parsed["model"]]
    parts = [parsed["noun"], shape, *parsed["type"], *model, *colors, size]
    return _text(" ".join(p for p in parts if p), MAX_TITLE)


def product_shape(product, specs, size: str) -> str:
    spec_shape = _spec(specs, "форма")
    if spec_shape:
        return spec_shape
    parsed = parse_title(product.title)
    if parsed["shape_noun"]:
        return parsed["shape_noun"]
    if _DIAMETER_RE.match(size or ""):
        return "Круг"
    return ""


def product_color(product, specs) -> str:
    """Google color: title colors (≤3, '/'), else active_color, else spec."""
    colors = parse_title(product.title)["colors"]
    if colors:
        return "/".join(c[:40] for c in colors[:3])
    return (_product_color(product) or _spec(specs, "колір", "цвет", "color"))[:100]


# --- feed -------------------------------------------------------------------


def _tag(name: str, value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, dict):
        inner = "".join(_tag(k, v) for k, v in value.items())
        return f"<g:{name}>{inner}</g:{name}>" if inner else ""
    return f"<g:{name}>{escape(str(value))}</g:{name}>"


def _image_urls(product) -> list[str]:
    urls = []
    # products/default.png is the upload placeholder: Google flags it as a
    # generic image and disapproves the item, so it never becomes image_link.
    if product.image and not product.image.name.endswith("default.png"):
        urls.append(absolute_site_url(product.image.url))
    for img in sorted(product.images.all(), key=lambda i: (i.sort_order, i.pk)):
        if img.image:
            urls.append(absolute_site_url(img.image.url))
    return urls


def variant_link(product, attr) -> str:
    return absolute_site_url(f"{product.get_absolute_url()}?{SIZE_PARAM}={attr.pk}")


COUNTRY_CATEGORIES = ("Українські", "Турецькі")
PRICE_BANDS = ((500, "до 500 грн"), (1000, "500-999 грн"), (2500, "1000-2499 грн"))
SIZE_CLASSES = ((1.0, "малий"), (4.0, "середній"))


def feed_product_type(categories) -> str:
    """`Килими > <country> > <room>` from shop categories (Ads can split by it)."""
    titles = [c.title.strip() for c in categories if (c.title or "").strip()]
    if not titles:
        return ""
    countries = [t for t in titles if t in COUNTRY_CATEGORIES]
    rooms = [t for t in titles if t not in COUNTRY_CATEGORIES]
    return " > ".join(["Килими", *countries[:1], *rooms[:1]])


def price_band(price) -> str:
    value = Decimal(str(price or 0))
    for limit, label in PRICE_BANDS:
        if value < limit:
            return label
    return "від 2500 грн"


def size_class(dims) -> str:
    if not dims:
        return ""
    area = dims[0] * dims[1] / 10000
    for limit, label in SIZE_CLASSES:
        if area < limit:
            return label
    return "великий"


def description_with_facts(description: str, size: str, color: str, material: str) -> str:
    """Append a short facts line (size/color/material from the DB) so Google
    can match descriptive queries; skipped facts are simply left out."""
    facts = []
    if size:
        facts.append(f"Розмір: {size}.")
    if color:
        facts.append(f"Колір: {color.replace('/', ', ')}.")
    if material:
        facts.append(f"Матеріал: {material.lower()}.")
    if not facts:
        return description
    line = " ".join(facts)
    if not description:
        return line
    room = MAX_DESCRIPTION - len(line) - 2
    return f"{description[:room].rstrip()}\n\n{line}"


def _details(specs: list[tuple[str, str]], shape: str) -> list[dict]:
    rows = list(specs)
    if shape and not _spec(specs, "форма"):
        rows.append(("Форма", shape))
    return [
        {
            "section_name": DETAIL_SECTION,
            "attribute_name": name[:140],
            "attribute_value": value[:1000],
        }
        for name, value in rows
    ]


def build_items(products) -> list[dict]:
    items: list[dict] = []
    for product in products:
        images = _image_urls(product)
        if not images:
            continue  # Google rejects items without image_link
        specs = product_specs(product)
        description = product_description(product)
        color = product_color(product, specs)
        material = _spec(specs, "матеріал", "склад", "материал")[:200]
        pattern = _spec(specs, "малюн", "візерун", "орнамент", "дизайн", "принт")[:100]
        highlights = [f"{n}: {v}"[:150] for n, v in specs][:10]
        categories = list(product.categories.all())
        product_type = feed_product_type(categories)
        google_category = _google_product_category(product)

        attrs = sorted(product.product_attr.all(), key=lambda a: (a.sort_order, a.pk))
        for attr in attrs:
            if attr.custom_attribute or not attr.price:
                continue
            size = format_size(attr.size.title if attr.size else "")
            dims = size_dimensions(size)
            shape = product_shape(product, specs, size)
            total = attr.get_total_price()
            item = {
                "id": f"{product.pk}-{attr.pk}",
                "item_group_id": str(product.pk),
                "title": feed_title(product, size, specs, color),
                "description": description_with_facts(description, size, color, material),
                "link": variant_link(product, attr),
                "image_link": images[0],
                "additional_image_link": images[1 : 1 + MAX_ADDITIONAL_IMAGES],
                "availability": "in_stock" if (attr.quantity or 0) > 0 else "out_of_stock",
                "price": _money(attr.price),
                "sale_price": _money(total) if attr.discount and total != attr.price else "",
                "condition": "new",
                "brand": ORG_NAME,
                "identifier_exists": "no",
                "google_product_category": google_category,
                "product_type": product_type,
                "size": size,
                "color": color,
                "material": material,
                "pattern": pattern,
                "product_width": f"{dims[0]} cm" if dims else "",
                "product_length": f"{dims[1]} cm" if dims else "",
                "product_detail": _details(specs, shape),
                # Google wants 2+ highlights; a single spec line is noise.
                "product_highlight": highlights if len(highlights) >= 2 else [],
                # Ads bidding splits: price band of the variant, size class, shape.
                "custom_label_0": price_band(total),
                "custom_label_1": size_class(dims),
                "custom_label_2": shape.lower() if shape else "",
            }
            items.append(item)
    return items


def render_feed(items: list[dict]) -> str:
    base = absolute_site_url("/").rstrip("/")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">',
        "<channel>",
        f"<title>{escape(ORG_NAME)}</title>",
        f"<link>{escape(base)}</link>",
        "<description>Килими mr.Carpet</description>",
    ]
    for item in items:
        parts.append("<item>")
        for key, value in item.items():
            if isinstance(value, list):
                parts.extend(_tag(key, v) for v in value)
            else:
                parts.append(_tag(key, value))
        parts.append("</item>")
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(p for p in parts if p)


def feed_products():
    from catalog.models import Product

    return (
        Product.objects.all()
        .select_related("active_color")
        .prefetch_related(
            "categories",
            "images",
            "product_attr__size",
            "product_specs__specification",
            "product_specs__spec_value",
        )
    )


def build_feed() -> str:
    return render_feed(build_items(feed_products()))
