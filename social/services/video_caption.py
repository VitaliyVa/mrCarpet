"""
Captions for the daily video, one render per network.

One structure of facts, several renders — not five independently written
texts that drift apart the first time the product model changes.

The rule every render obeys: **the price must not be readable before the
video is watched.** The whole format asks the viewer to guess it. How that
rule applies depends on how much of the caption the network shows up front:

* TikTok, Instagram, Facebook truncate after a line or two behind a "more"
  link, so the full size list may appear further down where it informs
  rather than spoils.
* Threads shows the whole post at once. There is no "further down", so the
  prices are left out entirely.
* YouTube needs a title, which is the most visible text of all — it gets the
  hook question and nothing else.
"""

from __future__ import annotations

from social.models import VideoDelivery
from social.services.post_content import build_product_content, render_plain
from social.services.tiktok_script import (
    BASE_HASHTAGS,
    CATEGORY_HASHTAGS,
    CTA,
    build_script,
)

# What each network accepts. Facebook's real ceiling is far higher, but a
# caption nobody scrolls is not worth the extra characters.
CAPTION_LIMITS = {
    VideoDelivery.Platform.TIKTOK: 2200,
    VideoDelivery.Platform.INSTAGRAM: 2200,
    VideoDelivery.Platform.FACEBOOK: 5000,
    VideoDelivery.Platform.THREADS: 480,
    VideoDelivery.Platform.YOUTUBE: 4800,
}

YOUTUBE_TITLE_LIMIT = 100

BIO_LINE = "🛒 Каталог — лінк у профілі"

# Tags derived from what the product actually is, keyed by (spec, value).
#
# Curated rather than generated: a value is only worth a tag if a human might
# type it into a search box. "Овал" becomes #овальнийкилим because people look
# for oval rugs; "Поліпропілен" gets nothing because nobody searches by
# polymer. Mechanically turning every spec into a hashtag would bury the two
# or three that carry weight.
SPEC_TAGS: dict[tuple[str, str], str] = {
    ("Форма килима", "Овал"): "овальнийкилим",
    ("Форма килима", "Круглий"): "круглийкилим",
    ("Форма килима", "Квадрат"): "квадратнийкилим",
    ("Форма килима", "Напівколо"): "килимнапівколо",
    ("Виробник", "Україна"): "українськийкилим",
    ("Виробник", "Туреччина"): "турецькийкилим",
    ("Виробник", "Турція"): "турецькийкилим",
    ("Виробник", "Бельгія"): "бельгійськийкилим",
    ("Склад килима", "Шовк"): "шовковийкилим",
    ("Склад килима", "Гума"): "гумовийкилим",
    ("Основа", "Джут"): "джутовийкилим",
    ("Основа", "Резина"): "неслизькийкилим",
    ("Висота ворса", "Безворсовий"): "безворсовийкилим",
}

#: Pile height arrives as "6.5 мм". The number itself is not a search term,
#: but "long pile" and "short pile" are, so it is bucketed.
LONG_PILE_MM = 15.0


def _pile_tag(value: str) -> str:
    raw = (value or "").replace(",", ".").replace("мм", "").strip()
    try:
        mm = float(raw)
    except ValueError:
        return ""
    return "довгийворс" if mm >= LONG_PILE_MM else "короткийворс"


def spec_tags(product) -> list[str]:
    """Hashtags describing this particular rug, not rugs in general."""
    out: list[str] = []
    try:
        specs = product.product_specs.select_related("specification", "spec_value")
    except Exception:
        return out

    for spec in specs:
        name = (getattr(spec.specification, "title", "") or "").strip()
        value = (getattr(spec.spec_value, "title", "") or "").strip()
        if not name or not value:
            continue
        tag = SPEC_TAGS.get((name, value))
        if not tag and name == "Висота ворса":
            tag = _pile_tag(value)
        if tag and tag not in out:
            out.append(tag)
    return out


def _tags_for(product) -> list[str]:
    """
    Specific first, generic last.

    Order matters wherever the list gets truncated — Threads takes one tag,
    YouTube fifteen. The tag that says "oval jute rug" is worth more than the
    one that says "rugs", so it goes first and survives the cut.
    """
    tags: list[str] = []
    for category in product.categories.all():
        tag = CATEGORY_HASHTAGS.get((category.title or "").strip())
        if tag and tag not in tags:
            tags.append(tag)
    for tag in spec_tags(product):
        if tag not in tags:
            tags.append(tag)
    for tag in BASE_HASHTAGS:
        if tag not in tags:
            tags.append(tag)
    return tags


def hashtags_for(product, platform: str) -> str:
    """Inline hashtag block. Not used for Threads — see threads_topic_tag."""
    return " ".join(f"#{tag}" for tag in _tags_for(product))


def threads_topic_tag(product) -> str:
    """
    The single topic tag a Threads post is allowed.

    Documented, not a guess: "Only one topic tag is allowed per post, so the
    first valid tag included in a post ... is treated as the tag for that
    post." A wall of inline hashtags would render as plain text, read as
    engagement bait, and gain nothing.

    The most specific tag wins, which is simply the first: _tags_for orders
    category and product specifics ahead of the generic ones. Slicing by the
    length of BASE_HASHTAGS used to work here and broke the moment that order
    changed — position is a poor way to ask "which is the specific one".
    """
    chosen = (_tags_for(product) or [""])[0]
    # Meta's rules: 1–50 chars, no dots or ampersands, never a bare number.
    chosen = chosen.replace(".", "").replace("&", "").strip()[:50]
    return "" if chosen.isdigit() else chosen


#: Campaign name shared by every network, so GA4 can answer both "how much
#: traffic does the daily video bring" and "which network brings it" from the
#: same data.
UTM_CAMPAIGN = "daily-video"
UTM_MEDIUM = "video"


def product_url_for(product, platform: str) -> str:
    """
    The product link, tagged so GA4 can tell the networks apart.

    Platform metrics answer "who watched"; this answers "who came and bought".
    The second question is the one worth optimising for, and it is the only
    one we can measure without asking any platform for extra permissions.
    """
    from urllib.parse import urlencode

    content = build_product_content(product)
    if not content.url:
        return ""
    params = urlencode(
        {
            "utm_source": platform,
            "utm_medium": UTM_MEDIUM,
            "utm_campaign": UTM_CAMPAIGN,
        }
    )
    joiner = "&" if "?" in content.url else "?"
    return f"{content.url}{joiner}{params}"


def _fits(text: str, limit: int) -> str:
    """
    Trim to `limit`, counting whichever of characters or UTF-8 bytes binds first.

    Meta documents the 500 limit in characters but counts URLs and emoji in
    bytes, and does not say which applies to Cyrillic — where every character
    is two bytes. Respecting both costs us nothing here (our Threads text is
    short) and avoids a post silently truncated mid-word.
    """
    text = text[:limit]
    while len(text.encode("utf-8")) > limit:
        text = text[:-1]
    return text


def build_caption(pick, script: dict | None = None, *, platform: str) -> str:
    """Caption for one network. Distinct from the copy burned into the video."""
    product = pick.product
    script = script or build_script(pick)
    limit = CAPTION_LIMITS.get(platform, 2200)

    if platform == VideoDelivery.Platform.THREADS:
        return _threads_caption(product, script, limit=limit)
    if platform == VideoDelivery.Platform.YOUTUBE:
        return _youtube_description(product, script, limit=limit)
    if platform == VideoDelivery.Platform.FACEBOOK:
        return _facebook_caption(product, script, limit=limit)
    return _feed_caption(product, script, platform=platform, limit=limit)


def _feed_caption(product, script: dict, *, platform: str, limit: int) -> str:
    """
    TikTok and Instagram: full product body, then the ask.

    Deliberately does not lead with the price. Both networks show the opening
    lines under the video before it is watched, so a price on line two answers
    the question the video just asked.

    No URL: neither network makes caption links clickable, so buyers are sent
    to the bio.
    """
    tail = "\n".join([CTA, BIO_LINE, "", hashtags_for(product, platform)])
    body = render_plain(
        build_product_content(product),
        max_len=max(limit - len(tail) - 2, 200),
        with_url=False,
        allow_friendly_outro=False,
    )
    return f"{body}\n\n{tail}"[:limit]


def _facebook_caption(product, script: dict, *, limit: int) -> str:
    """
    Facebook: the one network where a caption link is clickable.

    Sending people to the bio here would waste the only clickable surface we
    get, so the product URL goes in directly.
    """
    content = build_product_content(product)
    url = product_url_for(product, VideoDelivery.Platform.FACEBOOK)
    tail_parts = [CTA]
    if url:
        tail_parts.append(f"👉 Дивитись у каталозі: {url}")
    else:
        tail_parts.append(BIO_LINE)
    tail_parts += ["", hashtags_for(product, VideoDelivery.Platform.FACEBOOK)]
    tail = "\n".join(tail_parts)

    body = render_plain(
        content,
        max_len=max(limit - len(tail) - 2, 200),
        with_url=False,
        allow_friendly_outro=False,
    )
    return f"{body}\n\n{tail}"[:limit]


def _threads_caption(product, script: dict, *, limit: int) -> str:
    """
    Threads: short, and entirely visible at once.

    That last part is what makes this different rather than merely shorter.
    With no "more" link there is nowhere to put the price where it will not be
    read before the video, so the size list is dropped and only the question
    survives. Anyone who wants the number watches, or asks.

    No hashtags in the text either: Threads allows one topic tag, and it is
    passed as its own parameter — see threads_topic_tag.

    The product link is not in the text: `link_attachment` renders it as a
    card and costs none of the 500-character budget.
    """
    return _fits(
        "\n".join([f"✨ {product.title}".strip(), "", script["hook"], "", CTA]),
        limit,
    )


def threads_alt_text(product, script: dict | None = None) -> str:
    """
    Describes the video for people who cannot see it.

    Accessibility first, but it also puts the concrete words — shape,
    material, maker — somewhere machine-readable, which the caption
    deliberately keeps free of clutter.
    """
    parts = [f"Відео: килим {product.title}".strip()]
    try:
        specs = product.product_specs.select_related("specification", "spec_value")
        details = [
            f"{(s.specification.title or '').strip().lower()}: "
            f"{(s.spec_value.title or '').strip()}"
            for s in specs
            if getattr(s, "specification", None) and getattr(s, "spec_value", None)
        ]
        if details:
            parts.append(", ".join(details))
    except Exception:
        pass
    parts.append("килим показано в інтер'єрі кімнати")
    return _fits(". ".join(parts), 1000)


def _youtube_description(product, script: dict, *, limit: int) -> str:
    """YouTube: the description is collapsed by default, so it may carry the lot."""
    content = build_product_content(product)
    url = product_url_for(product, VideoDelivery.Platform.YOUTUBE)
    tail_parts = [CTA]
    if url:
        tail_parts.append(f"👉 Каталог: {url}")
    tail_parts += ["", hashtags_for(product, VideoDelivery.Platform.YOUTUBE)]
    tail = "\n".join(tail_parts)

    body = render_plain(
        content,
        max_len=max(limit - len(tail) - 2, 200),
        with_url=False,
        allow_friendly_outro=False,
    )
    return f"{body}\n\n{tail}"[:limit]


#: YouTube is supposed to classify a Short from the file alone — vertical and
#: under three minutes — and our montage is 1080x1920 at 13s. It did not: the
#: first upload landed as an ordinary video. The hashtag is the historical
#: explicit signal and it is what actually works, so it is appended rather
#: than trusted to be unnecessary.
SHORTS_TAG = "#Shorts"


def build_youtube_title(pick, script: dict | None = None) -> str:
    """
    The title is the most visible text we write, so it carries the hook.

    A price here would be read in the feed before the video ever plays, so it
    stays out. The Shorts tag goes on the end, where it does not break the
    question a viewer reads first.
    """
    script = script or build_script(pick)
    hook = script["hook"]
    room = YOUTUBE_TITLE_LIMIT - len(SHORTS_TAG) - 1
    if len(hook) > room:
        hook = hook[:room].rstrip()
    return f"{hook} {SHORTS_TAG}"
