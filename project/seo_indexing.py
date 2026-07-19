"""SEO indexing switch (Phase 8 prep). Default OFF until explicit go-live."""

from __future__ import annotations

from django.conf import settings

SITE_CANONICAL_ORIGIN = "https://mrcarpet24.com"

# Paths that must stay blocked in prod robots.txt
ROBOTS_PROD_DISALLOW = (
    "/admin/",
    "/api/",
    "/cart/",
    "/basket/",
    "/checkout/",
    "/payment/",
    "/profile/",
    "/success/",
    "/favorite/",
    "/favourites/",
    "/password_reset/",
)


def is_indexing_enabled() -> bool:
    """True only when SEO_INDEXING_ENABLED is explicitly on (env/settings)."""
    return bool(getattr(settings, "SEO_INDEXING_ENABLED", False))


def build_robots_txt(*, sitemap_url: str | None = None) -> str:
    """
    DEV (default): Disallow: /
    PROD (SEO_INDEXING_ENABLED=True): Allow public + Sitemap + private Disallows
    """
    if not is_indexing_enabled():
        return (
            "# DEV: indexing closed (SEO_INDEXING_ENABLED=false)\n"
            "# Sitemap exists at /sitemap.xml for internal checks; crawlers are blocked\n"
            "# Go-live: set SEO_INDEXING_ENABLED=true (see docs/seo.md)\n"
            "User-agent: *\n"
            "Disallow: /\n"
        )

    sitemap = sitemap_url or f"{SITE_CANONICAL_ORIGIN}/sitemap.xml"
    lines = [
        "# PROD: indexing open (SEO_INDEXING_ENABLED=true)",
        "User-agent: *",
        "Allow: /",
    ]
    for path in ROBOTS_PROD_DISALLOW:
        lines.append(f"Disallow: {path}")
    lines.append(f"Sitemap: {sitemap}")
    lines.append("")
    lines.append(
        "# AI crawlers (GEO): do not add GPTBot/ClaudeBot/PerplexityBot "
        "Disallow while Allow: / is public"
    )
    lines.append("")
    return "\n".join(lines)
