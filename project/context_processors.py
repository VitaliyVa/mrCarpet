from project.free_shipping import delivery_terms, get_shop_settings
from project.seo_analytics import analytics_context, analytics_user_id
from project.seo_indexing import is_indexing_enabled
from project.seo_jsonld import dumps_jsonld, organization_graph, website_graph
from project.seo_urls import (
    canonical_query,
    canonical_url,
    google_review_url,
    has_content_query,
    site_base,
)


def seo_jsonld(request):
    """Sitewide Organization + WebSite JSON-LD + indexing/analytics flags."""
    ctx = {
        "organization_jsonld": dumps_jsonld(organization_graph(request)),
        "website_jsonld": dumps_jsonld(website_graph(request)),
        "seo_indexing_enabled": is_indexing_enabled(),
        "canonical_url": canonical_url(request),
        "canonical_query": canonical_query(request),
        # search / filter / sort variants: crawlable, never indexed
        "seo_noindex_query": has_content_query(request),
        "site_url": site_base(),
        "google_review_url": google_review_url(),
    }
    ctx.update(analytics_context())
    ctx["ga4_user_id"] = analytics_user_id(getattr(request, "user", None))
    return ctx


def shop_settings(request):
    """Singleton shop options (free shipping threshold, etc.) and the
    delivery / return terms derived from them (`shop_terms`)."""
    try:
        settings = get_shop_settings()
    except Exception:
        return {"shop_settings": None, "shop_terms": None}
    try:
        terms = delivery_terms(settings)
    except Exception:
        terms = None
    return {"shop_settings": settings, "shop_terms": terms}
