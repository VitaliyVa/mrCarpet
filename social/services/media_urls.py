"""Public HTTPS URLs for platform crawlers (Meta / TikTok)."""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings


def site_base() -> str:
    return (getattr(settings, "SITE_URL", None) or "https://mrcarpet24.com").rstrip("/")


def absolute_media_url(file_field) -> str:
    if not file_field:
        return ""
    try:
        url = file_field.url
    except ValueError:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{site_base()}{url}"


def product_share_url(post) -> str:
    base = site_base()
    path = ""
    product = getattr(post, "product", None)
    if product is not None:
        try:
            path = product.get_absolute_url()
        except Exception:
            slug = getattr(product, "slug", "") or ""
            path = f"/catalog/product/{slug}/" if slug else "/catalog/"
    else:
        path = "/catalog/"

    params = {
        "utm_source": "social",
        "utm_medium": "video",
        "utm_campaign": (getattr(post, "utm_campaign", None) or "social").strip()
        or "social",
    }
    promo = (getattr(post, "promo_code", None) or "").strip()
    if promo:
        params["promo"] = promo
    return f"{base}{path}?{urlencode(params)}"


#: utm_source per network. Anything unknown is reported as-is, lowercased.
ARTICLE_UTM_SOURCES = {
    "instagram": "instagram",
    "ig": "instagram",
    "facebook": "facebook",
    "fb": "facebook",
    "tiktok": "tiktok",
    "tt": "tiktok",
}


def article_campaign(article) -> str:
    return f"blog-{getattr(article, 'slug', '') or ''}".rstrip("-")


def article_share_url(article, platform: str, campaign: str | None = None) -> str:
    """
    https://mrcarpet24.com/blog/article/<slug>/?utm_source=instagram&utm_medium=social&utm_campaign=blog-<slug>

    Built from SITE_URL, never from a request, so the link in a post is the
    canonical one whatever host rendered it.
    """
    key = (platform or "").strip().lower()
    source = ARTICLE_UTM_SOURCES.get(key, key or "social")
    params = {
        "utm_source": source,
        "utm_medium": "social",
        "utm_campaign": (campaign or "").strip() or article_campaign(article),
    }
    return f"{site_base()}{article.get_absolute_url()}?{urlencode(params)}"


def post_share_url(post, platform: str) -> str:
    """The link a post carries: its article if it announces one, else the product."""
    article = getattr(post, "article", None) if getattr(post, "article_id", None) else None
    if article is not None:
        campaign = (getattr(post, "utm_campaign", "") or "").strip()
        if campaign in ("", "social"):
            campaign = article_campaign(article)
        return article_share_url(article, platform, campaign)
    return product_share_url(post)


def build_caption(post, platform: str) -> str:
    text = post.caption_for(platform)
    url = post_share_url(post, platform)
    if url and url not in text:
        text = f"{text}\n\n{url}".strip() if text else url
    return text[:2200]
