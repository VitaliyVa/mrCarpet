"""XML sitemaps for storefront (Phase 3). Indexing still closed via robots/noindex."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import Article
from catalog.models import Product, ProductCategory


class StaticViewSitemap(Sitemap):
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return [
            "index",
            "catalog",
            "all_collection",
            "about",
            "delivery",
            "faq",
            "refund",
            "terms",
            "policy",
            "blog",
        ]

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    """In-stock products (storefront manager). Each color variant = own URL."""

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
        return ProductCategory.objects.all().only("id", "slug")

    def lastmod(self, obj):
        return None


class ArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Article.objects.all().only("id", "slug", "updated")

    def lastmod(self, obj):
        return obj.updated


sitemaps = {
    "static": StaticViewSitemap,
    "products": ProductSitemap,
    "categories": CategorySitemap,
    "articles": ArticleSitemap,
}
