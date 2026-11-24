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


def get_seo_guides(category=None, limit: int = 3):
    """Public blog articles for the «Корисні статті» block (empty if none).

    With a category: articles about it first, i.e. those whose blog topic
    points at the category page (`ArticleTopic.target_path`) or whose text
    links to it, newest first; the rest of the places go to the newest public
    articles. Without one (the whole collection): the newest articles.
    """
    from django.db.models import Q

    from blog.models import Article

    fields = ("id", "title", "slug", "description", "image", "meta_description")
    order = ("-published_at", "-created", "-pk")
    public = Article.objects.public()

    matched = []
    path = category.get_absolute_url() if category is not None else ""
    if path:
        matched = list(
            public.filter(
                Q(topics__target_path__in=(path, path.rstrip("/")))
                | Q(description__contains=path)
            )
            .distinct()
            .order_by(*order)
            .only(*fields)[:limit]
        )
    if len(matched) >= limit:
        return matched
    rest = (
        public.exclude(pk__in=[a.pk for a in matched])
        .order_by(*order)
        .only(*fields)[: limit - len(matched)]
    )
    return matched + list(rest)
