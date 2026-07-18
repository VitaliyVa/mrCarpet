from project.free_shipping import get_shop_settings
from project.seo_analytics import analytics_context
from project.seo_indexing import is_indexing_enabled
from project.seo_jsonld import dumps_jsonld, organization_graph


def seo_jsonld(request):
    """Sitewide Organization JSON-LD + indexing/analytics flags for templates."""
    ctx = {
        "organization_jsonld": dumps_jsonld(organization_graph(request)),
        "seo_indexing_enabled": is_indexing_enabled(),
    }
    ctx.update(analytics_context())
    return ctx


def shop_settings(request):
    """Singleton shop options (free shipping threshold, etc.)."""
    try:
        settings = get_shop_settings()
    except Exception:
        return {"shop_settings": None}
    return {"shop_settings": settings}
