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


def build_caption(post, platform: str) -> str:
    text = post.caption_for(platform)
    url = product_share_url(post)
    if url and url not in text:
        text = f"{text}\n\n{url}".strip() if text else url
    return text[:2200]
