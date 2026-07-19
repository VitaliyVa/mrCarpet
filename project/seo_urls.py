"""Absolute public URLs forced to https SITE_URL (canonical / og:url)."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from django.conf import settings


def site_base() -> str:
    return (getattr(settings, "SITE_URL", "") or "https://mrcarpet24.com").rstrip("/")


def absolute_site_url(path: str = "/") -> str:
    """Join SITE_URL with a path; always https host from settings."""
    base = site_base()
    if not path:
        return base + "/"
    if path.startswith("http://") or path.startswith("https://"):
        parts = urlsplit(path)
        return urlunsplit(
            ("https", urlsplit(base).netloc, parts.path or "/", parts.query, "")
        )
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def canonical_url(request) -> str:
    """
    Prefer SITE_URL + path/query so canonical is never http:// behind TLS proxy.
    Falls back to request.build_absolute_uri() with http→https rewrite.
    """
    try:
        path = request.get_full_path()
    except Exception:
        path = "/"
    url = absolute_site_url(path)
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    return url
