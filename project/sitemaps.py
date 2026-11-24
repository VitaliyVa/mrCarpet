"""XML sitemaps for storefront (Phase 3). Indexing still closed via robots/noindex."""

from urllib.parse import urlsplit

from django.contrib.sitemaps import Sitemap as DjangoSitemap
from django.urls import reverse

from blog.models import Article
from catalog.models import Product, ProductCategory
from project.seo_jsonld import article_modified_at
from project.seo_urls import site_base


class Sitemap(DjangoSitemap):
    """<loc> always on SITE_URL (project.seo_urls), never the request host.

    Django builds every <loc> from the host and scheme the sitemap was
    fetched with: through an IP, a www alias or plain http it would list
    URLs that are not the canonical ones."""

    def get_protocol(self, protocol=None):
        return urlsplit(site_base()).scheme or "https"

    def get_domain(self, site=None):
        return urlsplit(site_base()).netloc


class StaticViewSitemap(Sitemap):
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        items = [
            "index",
            "catalog",
            "all_collection",
            "about",
            "delivery",
            "contacts",
            "faq",
            "refund",
            "terms",
            "policy",
            "blog",
        ]
        # «Акції» only while something is discounted: empty, it is noindex.
        from catalog.promotions import discounted_in_stock_products

        if discounted_in_stock_products().exists():
            items.append("stock")
        return items

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    """All products, in stock or not (OOS pages stay live with OutOfStock). Each color variant = own URL."""

    changefreq = "daily"
    priority = 0.9

    def items(self):
        return Product.objects.all().only("id", "slug", "updated")

    def lastmod(self, obj):
        return obj.updated


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        # Empty categories are not offered to Google. "Для ванни" and
        # "Акрилові килими" both had zero products and both sat in the
        # sitemap: an invitation to index a page that shows nothing, which
        # reads as thin content and wastes a visit if it ever ranks.
        # They come back automatically once they hold something.
        from django.db.models import Count

        return (
            ProductCategory.objects.annotate(n=Count("products"))
            .filter(n__gt=0)
            .only("id", "slug")
        )

    def lastmod(self, obj):
        return None


class ArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        # Drafts must not be advertised to Google. Saving used to publish
        # instantly, so this listed half-written articles by construction.
        return (
            Article.objects.public()
            .only("id", "slug", "updated", "published_at")
        )

    def lastmod(self, obj):
        # Scheduled articles are saved before they go live: lastmod is the
        # later of updated and published_at, never a date before publication.
        return article_modified_at(obj)


class SizeLandingSitemap(Sitemap):
    """/catalog/rozmir/<size>/ pages that exist right now (enough stock).

    A size that drops below the minimum is a 404 and leaves the list on
    the next fetch; it comes back on its own when stock returns."""

    changefreq = "weekly"
    priority = 0.7

    def items(self):
        from catalog.size_landings import landing_slugs

        return [chip.slug for chip in landing_slugs()]

    def location(self, item):
        from catalog.size_landings import landing_url

        return landing_url(item)


sitemaps = {
    "static": StaticViewSitemap,
    "products": ProductSitemap,
    "categories": CategorySitemap,
    "sizes": SizeLandingSitemap,
    "articles": ArticleSitemap,
}
