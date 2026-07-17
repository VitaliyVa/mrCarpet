"""Pre-flight checks before flipping SEO_INDEXING_ENABLED (Phase 8). Does NOT enable indexing."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.test import Client

from project.seo_indexing import build_robots_txt, is_indexing_enabled


class Command(BaseCommand):
    help = (
        "SEO go-live readiness report. Never enables indexing — "
        "only audits content/robots/meta prep."
    )

    def handle(self, *args, **options):
        enabled = is_indexing_enabled()
        self.stdout.write("")
        self.stdout.write("=== SEO Phase 8 readiness ===")
        self.stdout.write(
            f"SEO_INDEXING_ENABLED = {enabled} "
            f"(settings={getattr(settings, 'SEO_INDEXING_ENABLED', None)})"
        )
        if enabled:
            self.stdout.write(
                self.style.WARNING(
                    "⚠ Indexing flag is ON. If this is accidental — set "
                    "SEO_INDEXING_ENABLED=false immediately."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("✓ Indexing still closed (expected for prep).")
            )

        robots = build_robots_txt()
        if "Disallow: /\n" in robots or robots.rstrip().endswith("Disallow: /"):
            self.stdout.write(self.style.SUCCESS("✓ robots.txt builder → full Disallow"))
        else:
            self.stdout.write(self.style.WARNING("⚠ robots.txt builder is NOT full Disallow"))

        client = Client()
        resp = client.get("/robots.txt")
        body = resp.content.decode("utf-8", errors="replace")
        self.stdout.write(f"/robots.txt status={resp.status_code}")
        if "Disallow: /" in body and "Allow: /" not in body:
            self.stdout.write(self.style.SUCCESS("✓ Live /robots.txt blocks all crawlers"))
        else:
            self.stdout.write(self.style.ERROR("✗ Live /robots.txt unexpected:\n" + body))

        # Content gaps
        from blog.models import Article
        from catalog.models import Product, ProductCategory

        products = Product.admin_objects.all()
        total_p = products.count()
        missing_meta = products.filter(meta_description__isnull=True).count()
        missing_meta += (
            products.exclude(meta_description__isnull=True)
            .filter(meta_description="")
            .count()
        )
        missing_title_meta = products.filter(meta_title__isnull=True).count()
        missing_title_meta += (
            products.exclude(meta_title__isnull=True).filter(meta_title="").count()
        )

        cats = ProductCategory.objects.all()
        total_c = cats.count()
        missing_c_meta = (
            cats.filter(meta_description__isnull=True).count()
            + cats.exclude(meta_description__isnull=True)
            .filter(meta_description="")
            .count()
        )

        articles = Article.objects.all()
        total_a = articles.count()
        missing_a_meta = (
            articles.filter(meta_description__isnull=True).count()
            + articles.exclude(meta_description__isnull=True)
            .filter(meta_description="")
            .count()
        )

        self.stdout.write("")
        self.stdout.write("--- Content minimum ---")
        self.stdout.write(
            f"Products: {total_p} total, missing meta_description={missing_meta}, "
            f"missing meta_title={missing_title_meta}"
        )
        self.stdout.write(
            f"Categories: {total_c} total, missing meta_description={missing_c_meta}"
        )
        self.stdout.write(
            f"Articles: {total_a} total, missing meta_description={missing_a_meta}"
        )

        self.stdout.write("")
        self.stdout.write("--- Analytics (Phase 9) ---")
        from project.seo_analytics import analytics_context

        a = analytics_context()
        if a["analytics_enabled"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Analytics on (GA4={a['ga4_measurement_id'] or '—'} "
                    f"GTM={a['gtm_container_id'] or '—'})"
                )
            )
        else:
            self.stdout.write(
                "○ Analytics off (set GA4_MEASUREMENT_ID or GTM_CONTAINER_ID)"
            )
        if a["google_site_verification"]:
            self.stdout.write("✓ GOOGLE_SITE_VERIFICATION set")
        else:
            self.stdout.write("○ GOOGLE_SITE_VERIFICATION empty (optional for GSC meta)")

        self.stdout.write("")
        self.stdout.write("--- Go-live flip (DO NOT run until decision) ---")
        self.stdout.write("1. Fill remaining meta gaps (report above)")
        self.stdout.write("2. Set SEO_INDEXING_ENABLED=true in prod env")
        self.stdout.write("3. Restart web/nginx workers")
        self.stdout.write("4. Verify /robots.txt has Allow: / + Sitemap")
        self.stdout.write("5. Verify public PDP has robots index,follow")
        self.stdout.write("6. Verify /basket/ still noindex")
        self.stdout.write("7. GSC: add property → submit sitemap.xml")
        self.stdout.write("8. Spot-check Rich Results + AI citations")
        self.stdout.write("")
