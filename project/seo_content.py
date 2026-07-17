"""SEO/GEO content helpers (Phase 5) — TL;DR + latest guides for catalog."""

from __future__ import annotations

from django.utils.html import strip_tags

from project.text_encoding import fix_utf8_mojibake


def product_tldr(product) -> str:
    """2–3 sentence cite-friendly blurb under H1 (prefer meta_description)."""
    text = fix_utf8_mojibake((product.meta_description or "").strip())
    if not text:
        text = fix_utf8_mojibake(strip_tags(product.description or "").strip())
    if not text:
        return ""
    if len(text) <= 320:
        return text
    cut = text[:320].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{cut}…"


def get_seo_guides(limit: int = 3):
    """Latest blog articles for category/PDP cross-links (empty if none)."""
    from blog.models import Article

    return list(
        Article.objects.order_by("-created", "-pk").only(
            "id", "title", "slug", "description", "image", "meta_description"
        )[:limit]
    )
