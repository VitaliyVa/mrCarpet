"""Allowlist HTML sanitizer for blog CMS bodies (stdlib only)."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse


ALLOWED_TAGS = frozenset({"p", "h2", "h3", "ul", "ol", "li", "strong", "em", "a", "br"})
ALLOWED_ATTRS = {
    "a": frozenset({"href", "title"}),
}


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


class _AllowlistParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return
        if tag == "br":
            self._out.append("<br>")
            return
        allowed = ALLOWED_ATTRS.get(tag, frozenset())
        parts = [f"<{tag}"]
        for name, value in attrs:
            name = (name or "").lower()
            if name not in allowed:
                continue
            if name == "href":
                safe = _safe_href(value or "")
                if not safe:
                    continue
                value = safe
            esc = (
                (value or "")
                .replace("&", "&amp;")
                .replace('"', "&quot;")
                .replace("<", "&lt;")
            )
            parts.append(f' {name}="{esc}"')
        parts.append(">")
        self._out.append("".join(parts))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ALLOWED_TAGS and tag != "br":
            self._out.append(f"</{tag}>")

    def handle_data(self, data):
        if not data:
            return
        self._out.append(
            data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    def handle_entityref(self, name):
        self._out.append(f"&{name};")

    def handle_charref(self, name):
        self._out.append(f"&#{name};")

    def get_html(self) -> str:
        return "".join(self._out)


def sanitize_article_html(html: str) -> str:
    """Keep only allowlisted tags/attrs; drop scripts/events/unknown tags."""
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
