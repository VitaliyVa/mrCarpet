"""Allowlist HTML sanitizer for blog CMS bodies (stdlib only).

Two allowlists work together:

* ``ALLOWED_TAGS`` / ``ALLOWED_ATTRS`` say which elements and attributes may
  reach the page at all.
* ``ALLOWED_CLASSES`` says which ``class`` values each tag may carry. These are
  the article component kit (``bl-*``, documented in docs/blog-components.md)
  and nothing else, so an article can be laid out with callouts, tables and
  product cards without opening the door to arbitrary site CSS.

Tags are also balanced here. ``<div>`` is allowed now, and a stray ``</div>``
in an article body would otherwise close the page's own wrapper and drag the
sidebar and footer into the text column.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse


ALLOWED_TAGS = frozenset(
    {
        # text
        "p", "h2", "h3", "ul", "ol", "li", "strong", "em", "a", "br",
        # component kit
        "div", "span", "blockquote",
        "figure", "figcaption", "img",
        "table", "thead", "tbody", "tr", "th", "td",
        "details", "summary",
    }
)

VOID_TAGS = frozenset({"br", "img"})

#: Elements whose text must not leak into the page when the tag is dropped.
DROP_CONTENT_TAGS = frozenset({"script", "style", "iframe", "object", "template", "noscript"})

ALLOWED_ATTRS = {
    "a": frozenset({"href", "title", "class"}),
    "img": frozenset({"src", "alt", "width", "height", "class"}),
    "th": frozenset({"colspan", "rowspan", "scope"}),
    "td": frozenset({"colspan", "rowspan"}),
    "div": frozenset({"class"}),
    "p": frozenset({"class"}),
    "ul": frozenset({"class"}),
    "ol": frozenset({"class"}),
    "span": frozenset({"class"}),
    "blockquote": frozenset({"class"}),
    "figure": frozenset({"class"}),
}

#: The component kit. Anything not listed is stripped from ``class``.
ALLOWED_CLASSES = {
    "div": frozenset(
        {
            "bl-summary",
            "bl-callout", "bl-callout--tip", "bl-callout--note", "bl-callout--warning",
            "bl-proscons", "bl-pros", "bl-cons",
            "bl-table",
            "bl-gallery", "bl-gallery--3",
            "bl-faq",
            "bl-cta",
            # live product cards placeholder, carries data-products
            "blog-products",
        }
    ),
    "p": frozenset({"bl-proscons__title", "bl-cta__title", "bl-quote__author"}),
    "ul": frozenset({"bl-checklist"}),
    "ol": frozenset({"bl-steps"}),
    "blockquote": frozenset({"bl-quote"}),
    "figure": frozenset({"bl-figure--wide"}),
    "a": frozenset({"bl-product", "bl-btn"}),
    "img": frozenset({"bl-product__img"}),
    "span": frozenset(
        {
            "bl-product__body",
            "bl-product__title",
            "bl-product__text",
            "bl-product__price",
            "bl-product__more",
        }
    ),
}

_NUMERIC_ATTRS = frozenset({"width", "height", "colspan", "rowspan"})
_SCOPE_VALUES = frozenset({"col", "row"})


def _safe_href(value: str) -> str | None:
    href = (value or "").strip()
    if not href:
        return None
    lower = href.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        return None
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        # allow relative /faq/, /catalog/, #anchor
        if href.startswith(("/", "#", "?")):
            return href
        return None
    return href


def _safe_src(value: str) -> str | None:
    """Images: site-relative paths or https only. No data:, no protocol-relative."""
    src = (value or "").strip()
    if not src:
        return None
    if src.startswith("/") and not src.startswith("//"):
        return src
    parsed = urlparse(src)
    if parsed.scheme == "https" and parsed.netloc:
        return src
    return None


def _safe_classes(tag: str, value: str) -> str | None:
    allowed = ALLOWED_CLASSES.get(tag, frozenset())
    kept: list[str] = []
    for name in (value or "").split():
        if name in allowed and name not in kept:
            kept.append(name)
    return " ".join(kept) or None


def _is_products_placeholder(attrs) -> bool:
    for name, value in attrs:
        if (name or "").lower() == "class" and "blog-products" in (value or "").split():
            return True
    return False


def _clean_slug_list(value: str | None) -> str:
    """Keep «a-1,b_2» shapes only: lowercase letters, digits, - _ and commas."""
    text = re.sub(r"\s+", "", (value or "").lower())
    text = re.sub(r"[^a-z0-9_,-]", "", text)
    return ",".join(part for part in text.split(",") if part)


def _escape_attr(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )


class _AllowlistParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._stack: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP_CONTENT_TAGS:
            self._drop_depth += 1
            return
        if self._drop_depth or tag not in ALLOWED_TAGS:
            return
        if tag == "br":
            self._out.append("<br>")
            return
        if tag == "div" and _is_products_placeholder(attrs):
            # Live product cards: emitted in one fixed form so the renderer
            # (blog/services/product_cards.py) can find it with a strict
            # pattern. Only slug characters survive in the list.
            slugs = _clean_slug_list(dict((n.lower(), v) for n, v in attrs).get("data-products"))
            self._out.append(f'<div class="blog-products" data-products="{slugs}">')
            self._stack.append(tag)
            return
        allowed = ALLOWED_ATTRS.get(tag, frozenset())
        parts = [f"<{tag}"]
        seen: set[str] = set()
        for name, value in attrs:
            name = (name or "").lower()
            if name not in allowed or name in seen:
                continue
            value = value or ""
            if name == "href":
                value = _safe_href(value)
            elif name == "src":
                value = _safe_src(value)
            elif name == "class":
                value = _safe_classes(tag, value)
            elif name in _NUMERIC_ATTRS:
                value = value.strip() if value.strip().isdigit() else None
            elif name == "scope":
                value = value.strip().lower() if value.strip().lower() in _SCOPE_VALUES else None
            if not value and name != "alt":
                continue
            seen.add(name)
            parts.append(f' {name}="{_escape_attr(value)}"')
        if tag == "img":
            if "src" not in seen:
                return  # an <img> without a usable source is just a broken box
            if "alt" not in seen:
                parts.append(' alt=""')
            parts.append(' loading="lazy" decoding="async"')
            parts.append(">")
            self._out.append("".join(parts))
            return
        parts.append(">")
        self._out.append("".join(parts))
        self._stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        tag = tag.lower()
        if tag not in VOID_TAGS and tag not in DROP_CONTENT_TAGS:
            self.handle_endtag(tag)
        elif tag in DROP_CONTENT_TAGS:
            self._drop_depth = max(0, self._drop_depth - 1)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP_CONTENT_TAGS:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if self._drop_depth or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        if tag not in self._stack:
            return  # stray closer: never let it close the page's own markup
        while self._stack:
            open_tag = self._stack.pop()
            self._out.append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def handle_data(self, data):
        if not data or self._drop_depth:
            return
        self._out.append(
            data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    def handle_entityref(self, name):
        if not self._drop_depth:
            self._out.append(f"&{name};")

    def handle_charref(self, name):
        if not self._drop_depth:
            self._out.append(f"&#{name};")

    def get_html(self) -> str:
        closers = [f"</{tag}>" for tag in reversed(self._stack)]
        return "".join(self._out + closers)


def sanitize_article_html(html: str) -> str:
    """Keep only allowlisted tags/attrs/classes; drop scripts/events/unknown tags."""
    if not html:
        return ""
    parser = _AllowlistParser()
    try:
        parser.feed(str(html))
        parser.close()
    except Exception:
        # Broken markup → escape as plain-ish text via data-only path
        return (
            str(html)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
    return parser.get_html().strip()


def looks_like_html(text: str) -> bool:
    stripped = (text or "").lstrip()
    return stripped.startswith("<") and ">" in stripped[:40]
