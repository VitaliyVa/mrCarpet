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
