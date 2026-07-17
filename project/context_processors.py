from project.seo_jsonld import dumps_jsonld, organization_graph


def seo_jsonld(request):
    """Sitewide Organization JSON-LD for every storefront page."""
    return {
        "organization_jsonld": dumps_jsonld(organization_graph(request)),
    }
