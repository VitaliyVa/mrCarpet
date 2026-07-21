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

# Instagram counts hashtags against a limit of 30 and rewards specificity;
# Threads treats them as topic tags and a wall of them reads as spam.
MAX_HASHTAGS = {
    VideoDelivery.Platform.THREADS: 3,
}


def hashtags_for(product, platform: str) -> str:
    tags = list(BASE_HASHTAGS)
    for category in product.categories.all():
        tag = CATEGORY_HASHTAGS.get((category.title or "").strip())
        if tag and tag not in tags:
            tags.append(tag)
    limit = MAX_HASHTAGS.get(platform)
    if limit:
        tags = tags[:limit]
    return " ".join(f"#{tag}" for tag in tags)


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
    tail_parts = [CTA]
    if content.url:
        tail_parts.append(f"👉 Дивитись у каталозі: {content.url}")
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
    """
    lines = [
        f"✨ {product.title}".strip(),
        "",
        script["hook"],
        "",
        CTA,
        BIO_LINE,
    ]
    text = "\n".join(lines)
    tags = hashtags_for(product, VideoDelivery.Platform.THREADS)
    if tags and len(text) + len(tags) + 2 <= limit:
        text = f"{text}\n\n{tags}"
    return text[:limit]


def _youtube_description(product, script: dict, *, limit: int) -> str:
    """YouTube: the description is collapsed by default, so it may carry the lot."""
    content = build_product_content(product)
    tail_parts = [CTA]
    if content.url:
        tail_parts.append(f"👉 Каталог: {content.url}")
    tail_parts += ["", hashtags_for(product, VideoDelivery.Platform.YOUTUBE)]
    tail = "\n".join(tail_parts)

    body = render_plain(
        content,
        max_len=max(limit - len(tail) - 2, 200),
        with_url=False,
        allow_friendly_outro=False,
    )
    return f"{body}\n\n{tail}"[:limit]


def build_youtube_title(pick, script: dict | None = None) -> str:
    """
    The title is the most visible text we write, so it carries the hook only.

    A price here would be read in the feed before the video ever plays.
    """
    script = script or build_script(pick)
    return script["hook"][:YOUTUBE_TITLE_LIMIT]
