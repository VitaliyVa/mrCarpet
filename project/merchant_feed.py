"""Google Merchant Center product feed (RSS 2.0 + g: namespace).

One feed item per sellable size (ProductAttribute). Sizes of one product share
`item_group_id`, so Google shows them as variants of one listing. Meta's
catalog reads the same URL.

Facts only from the DB, nothing generated:
- brand: the manufacturer where known (a brand spec, Karat for its collections),
  else mr.Carpet; no GTIN (`identifier_exists=no`);
- no `mpn`: with `identifier_exists=no` an MPN contradicts the flag, and our
  pk is not a manufacturer part number;
- id is stable `<product.pk>-<attr.pk>`; `link` carries `?size=<attr.pk>` so
  the PDP opens with that size and its price already rendered (canonical
  stays the clean product URL);
- color / shape / type words are parsed from the shop-written title (and
  active_color / specs / the description's own colour words as fallback);
  material and `product_detail` come from ProductSpecification rows (same
  rows as the PDP `<dl>` and the JSON-LD `additionalProperty`); pattern from
  a «Малюнок» spec, else from clear title / description words;
- product_length / product_width come from the size label;
- `shipping` (Nova Poshta, free from the ShopSettings threshold, handling and
  transit days) comes from project.free_shipping, same as the JSON-LD.
Custom-size attributes (price per m², no fixed price) are skipped.
"""

from __future__ import annotations

import html
import re
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils.html import strip_tags

from project.seo_jsonld import ORG_NAME, _google_product_category, _product_color, product_brand
from project.seo_urls import absolute_site_url
from project.text_encoding import fix_utf8_mojibake

MAX_ADDITIONAL_IMAGES = 10
# Shortest width Google treats as a large product image; smaller main images
# are swapped for a big gallery photo (see _image_urls).
MIN_MAIN_IMAGE_WIDTH = 800
_IMAGE_WIDTHS: dict[str, int] = {}
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
    parsed = parse_title(product.title)
    title_noun = parsed["shape_noun"]
    if spec_shape:
        # a mistyped spec ('Прямокутник' on an oval rug) loses to the title,
        # which names what the buyer sees; wording-only differences
        # ('Круглий' vs 'Круг') keep the spec
        spec_shape_of = _shape_of(spec_shape)
        if title_noun and spec_shape_of and spec_shape_of[1] != title_noun:
            return title_noun
        return spec_shape
    if title_noun:
        return title_noun
    if _DIAMETER_RE.match(size or ""):
        return "Круг"
    return ""


def _named_color(product, specs) -> str:
    """Title colors (≤3, '/'), else active_color, else spec."""
    colors = parse_title(product.title)["colors"]
    if colors:
        return "/".join(c[:40] for c in colors[:3])
    return (_product_color(product) or _spec(specs, "колір", "цвет", "color"))[:100]


def product_color(product, specs) -> str:
    """Google color: title / active_color / spec, else the colour words the
    description gives the rug itself ('Бежевий з чорними плямками')."""
    return _named_color(product, specs) or description_color(product)[:100]


# --- description facts (colour / pattern words the shop wrote) --------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
# Sentences about another product ('Є такий самий однотонний', 'відрізняється
# малюнком', 'подивіться зелений килимок') or questions say nothing about this one.
_OTHER_PRODUCT_MARKERS = (
    "подивіться", "відрізняється", "беріть", "такий самий", "така сама", "таке саме",
    "такого ж", "з таким малюнком", "тієї ж серії", "як на більшому", "як на меншому",
    "менший килим", "більший килим",
)
_OTHER_PRODUCT_STARTS = ("є ", "якщо ")
# Colours of the room around the rug ('пасує до сірих меблів').
_DECOR_MARKERS = (
    "пасує", "поєднуєт", "подушк", "штор", "меблі", "покривал", "підлог", "підлоз",
    "стін", "плитк",
)
# Thin accent marks: 'з білими й синюватими розводами' is not the rug colour.
_ACCENT_WORDS = ("розвод", "прожилк", "штрих", "тріщин", "крапк")
_FLEX_ENDINGS = (
    "ий", "ій", "а", "я", "е", "є", "і", "ого", "его", "ього", "их", "іх", "им", "ім",
    "ими", "іми", "ою", "ею", "ьою", "у", "ю", "ому", "ьому", "ої", "ей",
)
_SOFT_STEMS = {"син"}  # синій / синя / синю
_VAGUE_COLOR_STEMS = {"темн", "кольоров"}  # 'темна середина', 'кольорові' say no colour
_NOT_COLOR_WORDS = {"біля", "сина", "сину", "сини"}  # preposition / noun, not білий / синій
# The sentence speaks about the rug's own colour ('Сіра доріжка', 'чорному фоні',
# 'у коричнево-бежевих тонах'), not about a picture on it ('Жовті очі', 'зеленою травою').
_RUG_COLOR_ANCHOR = re.compile(
    r"килим|доріжк|\bфон|\bтон(?:ах|ами|і|ів)?\b|палітр|відтін|\bкол(?:ір|ьор)"
    r"|малюн|візерун|орнамент"
)
_WORD = re.compile(r"[а-яіїєґʼ’'a-z0-9-]+", re.I)


def _own_sentences(product) -> list[str]:
    text = _clean(getattr(product, "description", "") or "")
    meta = _clean(getattr(product, "meta_description", "") or "")
    if len(meta) > len(text):
        text = meta
    sentences = []
    for raw in _SENTENCE_SPLIT.split(text):
        sentence = raw.strip()
        lower = sentence.lower()
        if not sentence or lower.endswith("?"):
            continue
        if lower.startswith(_OTHER_PRODUCT_STARTS) or any(m in lower for m in _OTHER_PRODUCT_MARKERS):
            continue
        sentences.append(sentence)
    return sentences


def _color_stem(part: str) -> str:
    """Longest colour stem the word part starts with ('' when none)."""
    best = ""
    for stem in _COLOR_STEMS:
        if part.startswith(stem) and len(stem) > len(best):
            best = stem
    return best


def color_base(word: str) -> str:
    """Inflected colour word -> masculine form ('чорними' -> 'чорний',
    'сіро-чорним' -> 'сіро-чорний', 'Сіра' -> 'сірий'); '' when not a colour."""
    lower = word.lower().strip(",.;:!()«»\"")
    if lower in _NOT_COLOR_WORDS:
        return ""
    parts = [p for p in lower.split("-") if p]
    if not parts or not _CYRILLIC.search(lower):
        return ""
    out = []
    for n, part in enumerate(parts):
        last = n == len(parts) - 1
        prefix = ""
        for pre in _COLOR_PREFIXES:
            if part.startswith(pre) and len(part) > len(pre):
                prefix, part = pre, part[len(pre):]
                break
        if not last:
            if part in _COLOR_PREFIXES or (_color_stem(part) and part.endswith("о")):
                out.append(prefix + part)
                continue
            return ""
        if part in _COLOR_NOUNS:
            out.append(prefix + part)
            continue
        stem = _color_stem(part)
        if not stem or part[len(stem):] not in _FLEX_ENDINGS:
            return ""
        if stem in _VAGUE_COLOR_STEMS and len(parts) == 1 and not prefix:
            return ""
        out.append(prefix + stem + ("ій" if stem in _SOFT_STEMS else "ий"))
    return "-".join(out)


def description_color(product) -> str:
    """Colours of the first own description sentence that names the rug
    colour ('Бежевий з чорними плямками' -> 'бежевий/чорний'), ≤3; '' when
    the text names none. Room-decor and accent-mark colours are skipped."""
    for sentence in _own_sentences(product):
        lower = sentence.lower()
        # 'Чорно-білий малюнок пасує до сірих меблів': only the part before
        # the room decor speaks about the rug.
        cut = min((lower.find(m) for m in _DECOR_MARKERS if m in lower), default=len(lower))
        lower = lower[:cut]
        words = _WORD.findall(lower)
        # 'Бежевий з чорними плямками': the sentence opens with the colour
        # ('Різнокольорові шматочки пазлу' always speaks about the whole rug).
        first = color_base(words[0]) if words else ""
        opens_with_color = bool(first) and (
            first.startswith("різнокольоров")
            or len(words) == 1
            or words[1] in {"з", "із", "зі", "та", "і", "й"}
            or lower.lstrip()[len(words[0]):].startswith(",")
        )
        if not (opens_with_color or _RUG_COLOR_ANCHOR.search(lower)):
            continue
        colors: list[str] = []
        for n, word in enumerate(words):
            base = color_base(word)
            if not base:
                continue
            after = " ".join(words[n + 1 : n + 4])
            if any(a in after for a in _ACCENT_WORDS):
                continue
            if base.startswith("різнокольоров"):
                return "різнокольоровий"
            if base not in colors:
                colors.append(base)
        if colors:
            return "/".join(c[:40] for c in colors[:3])
    return ""


PATTERN_SPEC_KEYS = ("малюн", "візерун", "орнамент", "дизайн", "принт")
_SOLID_RE = re.compile(r"\bоднотонн(?:ий|а|е)\b(?!\s+середин)|без\s+малюнк|без\s+візерунк")
_WITHOUT_RE = re.compile(r"\bбез\s+[^.,;:!]*")  # 'без квіточок і вензелів'
_TITLE_PATTERNS = (
    ("дитячий", re.compile(r"дитяч|міккі|пазл")),
    ("тварини", re.compile(r"\b(?:тигр|леопард|зебр|ведмед|котик|собак|зайч)")),
)
_TEXT_PATTERNS = (  # first match wins
    ("мармуровий", re.compile(r"мармур")),
    ("класичний", re.compile(
        r"вензел|медальйон|класичн\w*\s+(?:візерун|вензел|орнамент|малюн|килим)"
        r"|орнамент\w*\s+під\s+старовин|східн\w*\s+орнамент|мереживн\w*\s+орнамент"
    )),
    ("квітковий", re.compile(r"квіт")),
    ("рослинний", re.compile(r"\bлист(?:я|ям|оч|ок)|рослин")),
    ("абстрактний", re.compile(r"абстракт|розвод|меланж|потерт\w*\s+малюн|плямк")),
    ("смугастий", re.compile(r"смуг")),
    ("хвилястий", re.compile(r"хвил")),
    ("геометричний", re.compile(
        r"геометр|ромб|клітин|квадратик|меандр|\bкіл\b|\bкола\b|кругами|промен"
        r"|\bарок\b|\bарки\b|арками|клаптик|прямокутник(?:ів|ами)\b|навхрест|зигзаг"
    )),
)


def product_pattern(product, specs) -> str:
    """Google pattern: a «Малюнок» / «Візерунок» spec, else a short Ukrainian
    word from what the title and description say about the rug ('однотонний',
    'абстрактний', 'класичний', ...). '' when neither says it clearly."""
    spec = _spec(specs, *PATTERN_SPEC_KEYS)
    if spec:
        return spec[:100]
    title = _clean(product.title).lower()
    for value, regex in _TITLE_PATTERNS:
        if regex.search(title):
            return value
    text = " ".join([title, *_own_sentences(product)]).lower()
    if _SOLID_RE.search(text):
        return "однотонний"
    text = _WITHOUT_RE.sub(" ", text)
    for value, regex in _TEXT_PATTERNS:
        if regex.search(text):
            return value
    return ""


# --- feed -------------------------------------------------------------------


def offer_id(product, attr=None) -> str:
    """Feed `g:id` of one sellable size: `<product.pk>-<attr.pk>`.

    The single source of the id for the feed and every GA4 ecommerce item
    (view_item, cart lines, server-side purchase, page cards), so Google Ads
    cart data and dynamic remarketing can join GA4 items to Merchant offers.
    Cut-to-length (custom) and unpriced sizes are not in the feed, so they
    keep the bare product pk. `product` may be a Product or its pk.
    """
    product_pk = getattr(product, "pk", product)
    if (
        attr is not None
        and not getattr(attr, "custom_attribute", False)
        and getattr(attr, "price", None)
        and getattr(attr, "pk", None) is not None
    ):
        return f"{product_pk}-{attr.pk}"
    return str(product_pk)


def _tag(name: str, value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, dict):
        inner = "".join(_tag(k, v) for k, v in value.items())
        return f"<g:{name}>{inner}</g:{name}>" if inner else ""
    return f"<g:{name}>{escape(str(value))}</g:{name}>"


def _image_width(field) -> int:
    """Pixel width of a stored image (0 when unknown); read once per file name."""
    name = getattr(field, "name", "") or ""
    if not name:
        return 0
    if name in _IMAGE_WIDTHS:
        return _IMAGE_WIDTHS[name]
    try:
        width = int(field.width or 0)
    except Exception:  # missing file or unreadable image: keep the old order
        return 0
    _IMAGE_WIDTHS[name] = width
    return width


def _image_urls(product) -> list[str]:
    # products/default.png is the upload placeholder: Google flags it as a
    # generic image and disapproves the item, so it never becomes image_link.
    card = product.image
    if not card or card.name.endswith("default.png"):
        card = None
    # AI interior illustrations (is_ai) stay on the PDP only: Merchant Center
    # wants generated images labelled and rejects ones that misrepresent the
    # product, so they never go to the feed.
    gallery = [
        img.image
        for img in sorted(product.images.all(), key=lambda i: (i.sort_order, i.pk))
        if img.image and not getattr(img, "is_ai", False)
    ]
    fields = ([card] if card is not None else []) + gallery
    # The catalog card image is resized to 500px; Shopping tiles look soft
    # under 800px. Use the first large gallery photo (PDP order) as image_link
    # and keep the card image right after it as an additional image.
    if fields and _image_width(fields[0]) < MIN_MAIN_IMAGE_WIDTH:
        big = next(
            (f for f in gallery if f is not fields[0] and _image_width(f) >= MIN_MAIN_IMAGE_WIDTH),
            None,
        )
        if big is not None:
            fields = [big] + [f for f in fields if f is not big]
    urls: list[str] = []
    for field in fields:
        url = absolute_site_url(field.url)
        if url not in urls:
            urls.append(url)
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


def description_with_facts(
    description: str, size: str, color: str, material: str, pattern: str = ""
) -> str:
    """Append a short facts line (size/color/material/pattern from the DB) so
    Google can match descriptive queries; skipped facts are simply left out."""
    facts = []
    if size:
        facts.append(f"Розмір: {size}.")
    if color:
        facts.append(f"Колір: {color.replace('/', ', ')}.")
    if material:
        facts.append(f"Матеріал: {material.lower()}.")
    if pattern:
        facts.append(f"Малюнок: {pattern.lower()}.")
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


def _shop_settings_or_none():
    try:
        from project.free_shipping import get_shop_settings

        return get_shop_settings()
    except Exception:
        return None


def item_shipping(price, settings) -> dict | str:
    """`g:shipping` for one variant: Nova Poshta, free from the ShopSettings
    threshold, else the carrier "from" tariff. Same numbers and days as the
    JSON-LD shippingDetails (project.seo_jsonld.offer_shipping_details) and
    the /delivery/ page. "" (tag left out) when settings are unknown."""
    from project.free_shipping import (
        HANDLING_DAYS,
        SHIPPING_CARRIER,
        SHIPPING_COUNTRY,
        TRANSIT_DAYS,
        shipping_rate,
    )

    if settings is None:
        return ""
    rate = shipping_rate(price, settings)
    if rate is None:
        return ""
    return {
        "country": SHIPPING_COUNTRY,
        "service": SHIPPING_CARRIER,
        "price": _money(rate),
        "min_handling_time": HANDLING_DAYS[0],
        "max_handling_time": HANDLING_DAYS[1],
        "min_transit_time": TRANSIT_DAYS[0],
        "max_transit_time": TRANSIT_DAYS[1],
    }


def sale_effective_date(window) -> str:
    """`start/end` (ISO 8601, minutes, local offset) of a running sale."""
    from django.utils import timezone

    start, end = window
    return "/".join(
        timezone.localtime(moment).isoformat(timespec="minutes") for moment in (start, end)
    )


def build_items(products) -> list[dict]:
    from catalog.promotions import active_sale_windows

    # One query: the running sale (with an end date ahead) of every product.
    sale_windows = active_sale_windows()
    items: list[dict] = []
    shop_settings = _shop_settings_or_none()
    for product in products:
        images = _image_urls(product)
        if not images:
            continue  # Google rejects items without image_link
        specs = product_specs(product)
        description = product_description(product)
        title_color = _named_color(product, specs)
        color = title_color or description_color(product)[:100]
        material = _spec(specs, "матеріал", "склад", "материал")[:200]
        pattern = product_pattern(product, specs)
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
                "id": offer_id(product, attr),
                "item_group_id": str(product.pk),
                # Title keeps the named colour only: a description colour
                # ('бежевий/чорний') would rename approved offers.
                "title": feed_title(product, size, specs, title_color),
                "description": description_with_facts(description, size, color, material, pattern),
                "link": variant_link(product, attr),
                "image_link": images[0],
                "additional_image_link": images[1 : 1 + MAX_ADDITIONAL_IMAGES],
                "availability": "in_stock" if (attr.quantity or 0) > 0 else "out_of_stock",
                "price": _money(attr.price),
                "sale_price": _money(total) if attr.discount and total != attr.price else "",
                "shipping": item_shipping(
                    total if total is not None else attr.price, shop_settings
                ),
                "condition": "new",
                "brand": product_brand(product.title, specs)[0][:70],
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
            window = sale_windows.get(product.pk)
            if item["sale_price"] and window:
                # The discounted price is announced until the sale ends.
                # Only a sale still running: after its end the discount stays
                # on the size until an admin removes it, and an end date in
                # the past would make Google charge `price` while the page
                # still shows `sale_price`.
                item["sale_price_effective_date"] = sale_effective_date(window)
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
