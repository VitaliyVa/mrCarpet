"""Allowlist sanitizer for newsletter inner HTML (email-safe tables)."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse

ALLOWED_TAGS = frozenset(
    {
        "table",
        "tr",
        "td",
        "th",
        "tbody",
        "thead",
        "p",
        "span",
        "strong",
        "em",
        "b",
        "i",
        "a",
        "br",
        "img",
        "ul",
        "ol",
        "li",
        "div",
    }
)
ALLOWED_ATTRS = {
    "a": frozenset({"href", "title", "target", "style", "rel"}),
    "img": frozenset(
        {"src", "alt", "width", "height", "style", "border"}
    ),
    "table": frozenset(
        {"role", "width", "cellspacing", "cellpadding", "border", "align", "style"}
    ),
    "td": frozenset(
        {"align", "valign", "width", "height", "style", "bgcolor", "colspan", "rowspan"}
    ),
    "th": frozenset(
        {"align", "valign", "width", "height", "style", "bgcolor", "colspan", "rowspan"}
    ),
    "tr": frozenset({"align", "valign", "style"}),
    "p": frozenset({"style", "align"}),
    "span": frozenset({"style"}),
    "div": frozenset({"style", "align"}),
    "strong": frozenset({"style"}),
    "em": frozenset({"style"}),
    "b": frozenset({"style"}),
    "i": frozenset({"style"}),
    "ul": frozenset({"style"}),
    "ol": frozenset({"style"}),
    "li": frozenset({"style"}),
}

UNSUBSCRIBE_PLACEHOLDER = "{{unsubscribe_url}}"
UNSUBSCRIBE_FOOTER = (
    '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
    'style="margin-top:4px;">'
    '<tr><td align="center" style="padding:28px 16px 8px;">'
    '<table role="presentation" cellspacing="0" cellpadding="0" border="0">'
    "<tr>"
    '<td align="center" style="border:1px solid #d4cbc3;border-radius:999px;'
    "padding:10px 22px;background-color:#f7f2ec;\">"
    f'<a href="{UNSUBSCRIBE_PLACEHOLDER}" '
    'style="color:#8a7f76;text-decoration:none;font-size:12px;line-height:1.3;'
    'font-family:Arial,Helvetica,sans-serif;letter-spacing:0.02em;">'
    "Відписатися від розсилки</a>"
    "</td></tr></table>"
    "</td></tr></table>"
)


def _safe_href(value: str) -> str | None:
    href = (value or "").strip()
    if not href:
        return None
    if UNSUBSCRIBE_PLACEHOLDER in href:
        return href
    lower = href.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        return None
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in ("http", "https", "mailto"):
        if href.startswith(("/", "#", "?")):
            return href
        return None
    return href


def _safe_src(value: str) -> str | None:
    src = (value or "").strip()
    if not src:
        return None
    lower = src.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        return None
    parsed = urlparse(src)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return None
    return src


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
                value = _safe_href(value or "")
                if not value:
                    continue
            if name == "src":
                value = _safe_src(value or "")
                if not value:
                    continue
            if name == "style":
                style = value or ""
                if re.search(r"expression\s*\(|javascript:", style, re.I):
                    continue
                value = style
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


def _strip_ai_unsubscribe(html: str) -> str:
    """Remove AI / leftover unsub links; we always append our styled footer."""
    text = html or ""
    text = re.sub(
        r"(?is)<a\b[^>]*href=[\"'][^\"']*unsubscribe[^\"']*[\"'][^>]*>.*?</a>",
        "",
        text,
    )
    text = re.sub(
        r"(?is)<a\b[^>]*>\s*Відписатися[^<]*</a>",
        "",
        text,
    )
    text = text.replace(UNSUBSCRIBE_PLACEHOLDER, "")
    text = text.replace("&#123;&#123;unsubscribe_url&#125;&#125;", "")
    return text.strip()


def sanitize_newsletter_html(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"(?is)<!DOCTYPE.*?>", "", text)
    text = re.sub(r"(?is)</?(html|head|body|script|iframe|object|embed)[^>]*>", "", text)
    parser = _AllowlistParser()
    parser.feed(text)
    parser.close()
    html = parser.get_html().strip()
    html = html.replace("{{unsubscribe_url}}", UNSUBSCRIBE_PLACEHOLDER)
    html = html.replace(
        "&#123;&#123;unsubscribe_url&#125;&#125;", UNSUBSCRIBE_PLACEHOLDER
    )
    html = _strip_ai_unsubscribe(html)
    return f"{html}\n{UNSUBSCRIBE_FOOTER}"
