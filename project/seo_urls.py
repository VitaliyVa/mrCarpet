"""Absolute public URLs forced to https SITE_URL (canonical / og:url)."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit, urlunsplit

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


def google_review_url() -> str | None:
    """Link that opens Google's review form for the store, or None until
    GOOGLE_PLACE_ID is set (see core/settings.py)."""
    place_id = (getattr(settings, "GOOGLE_PLACE_ID", "") or "").strip()
    if not place_id:
        return None
    return f"https://search.google.com/local/writereview?placeid={place_id}"


# Query params that define distinct, indexable content. Everything else is
# dropped from canonical / og:url. Only `page` qualifies: filters, sort and
# search (`q`) are combinations of the same products, and ad/analytics
# params (gclid, utm_*, ...) are the same page with a tracking tail.
CANONICAL_KEEP_PARAMS = ("page",)

# Params that say who sent the visitor, not what the page shows. They never
# make a page noindex: an ad landing (?gclid=...) or a Merchant Center link
# (?srsltid=...) is still the real page, the canonical already points home.
TRACKING_PARAMS = frozenset(
    {
        "gclid",
        "gclsrc",
        "gbraid",
        "wbraid",
        "dclid",
        "gad_source",
        "gad_campaignid",
        "srsltid",
        "fbclid",
        "yclid",
        "ysclid",
        "ttclid",
        "msclkid",
        "twclid",
        "li_fat_id",
        "igshid",
        "epik",
        "s_kwcid",
        "ef_id",
        "rb_clickid",
        "wickedid",
        "ref",
        "ref_src",
        "fb_action_ids",
        "fb_action_types",
        "fb_source",
        "fb_ref",
        "spm",
    }
)
TRACKING_PARAM_PREFIXES = ("utm_", "_ga", "_gl", "mc_", "pk_", "mtm_", "hsa_", "oly_")


def is_tracking_param(key: str) -> bool:
    k = (key or "").strip().lower()
    return k in TRACKING_PARAMS or k.startswith(TRACKING_PARAM_PREFIXES)


def _split_full_path(request) -> tuple[str, list[tuple[str, str]]]:
    try:
        full = request.get_full_path()
    except Exception:
        full = "/"
    parts = urlsplit(full or "/")
    return parts.path or "/", parse_qsl(parts.query, keep_blank_values=True)


def _page_number(value: str) -> int | None:
    try:
        n = int((value or "").strip())
    except (TypeError, ValueError):
        return None
    return n if n > 1 else None


def has_content_query(request) -> bool:
    """
    True when the URL carries params that change what the listing shows
    (search `q`, filters, sort, anything unknown) — i.e. a page variant that
    must be `noindex, follow`. `page` and tracking params do not count.
    """
    _, items = _split_full_path(request)
    return any(
        k not in CANONICAL_KEEP_PARAMS and not is_tracking_param(k) for k, _ in items
    )


def canonical_query(request) -> str:
    """
    Query string to append to a canonical: "?page=N" for N > 1 on an
    otherwise clean URL, else "". A filtered/sorted/search URL points to the
    unfiltered listing's first page (its page 2 is not the clean page 2).
    """
    if has_content_query(request):
        return ""
    _, items = _split_full_path(request)
    page = None
    for k, v in items:
        if k == "page":
            page = _page_number(v)
    return f"?page={page}" if page else ""


def canonical_url(request) -> str:
    """
    SITE_URL + path + whitelisted query (see CANONICAL_KEEP_PARAMS), so
    canonical is never http:// behind the TLS proxy and never carries
    search/filter/sort/tracking params.
    """
    path, _ = _split_full_path(request)
    url = absolute_site_url(path + canonical_query(request))
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    return url
