"""Analytics / measurement helpers (SEO Phase 9)."""

from __future__ import annotations

from django.conf import settings


def ga4_measurement_id() -> str:
    return (getattr(settings, "GA4_MEASUREMENT_ID", "") or "").strip()


def gtm_container_id() -> str:
    return (getattr(settings, "GTM_CONTAINER_ID", "") or "").strip()


def google_site_verification() -> str:
    return (getattr(settings, "GOOGLE_SITE_VERIFICATION", "") or "").strip()


def analytics_enabled() -> bool:
    """True when GA4 and/or GTM is configured."""
    return bool(ga4_measurement_id() or gtm_container_id())


def analytics_context() -> dict:
    return {
        "ga4_measurement_id": ga4_measurement_id(),
        "gtm_container_id": gtm_container_id(),
        "google_site_verification": google_site_verification(),
        "analytics_enabled": analytics_enabled(),
        # Cache-bust for /static/source/pages/* (nginx immutable otherwise).
        "static_v": (getattr(settings, "STATIC_ASSET_VERSION", "") or "1").strip(),
        # Filled in request-aware processor when user is authenticated.
        "ga4_user_id": "",
    }


def analytics_user_id(user) -> str:
    """Stable GA4 user_id for logged-in users (never email)."""
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    pk = getattr(user, "pk", None)
    return f"u{pk}" if pk else ""
