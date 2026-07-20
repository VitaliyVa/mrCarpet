"""
TikTok OAuth token lifecycle.

TikTok issues an access_token valid for 24 hours and a refresh_token valid
for 365 days from the initial grant. There is no never-expiring token, so a
background refresh is mandatory: without it the integration works for exactly
one day after a human pastes a token.

The refresh response may carry a *new* refresh_token, and the old one dies as
soon as it does. Persisting both values on every refresh is what keeps the
integration alive; dropping the returned refresh_token is the single most
common way these integrations break.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from social.models import TikTokToken

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
HTTP_TIMEOUT = 30

# Exactly what the pipeline uses, and no more: requesting a scope the demo
# video cannot show it exercising is one of the commonest audit rejections.
# Direct Post goes through video.publish; the draft-upload path is never called.
SCOPES = ("user.info.basic", "video.publish")


class TikTokAuthError(RuntimeError):
    pass


def client_key() -> str:
    return (getattr(settings, "TIKTOK_CLIENT_KEY", "") or "").strip()


def client_secret() -> str:
    return (getattr(settings, "TIKTOK_CLIENT_SECRET", "") or "").strip()


def redirect_uri() -> str:
    configured = (getattr(settings, "TIKTOK_REDIRECT_URI", "") or "").strip()
    return configured or "https://mrcarpet24.com/api/tiktok/callback/"


def oauth_configured() -> bool:
    return bool(client_key() and client_secret())


def is_sandbox() -> bool:
    """Sandbox client keys are prefixed with 'sb' by TikTok."""
    return client_key().startswith("sb")


def build_authorize_url(state: str) -> str:
    if not oauth_configured():
        raise TikTokAuthError("TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET are empty")
    params = {
        "client_key": client_key(),
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "redirect_uri": redirect_uri(),
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def new_state() -> str:
    return secrets.token_urlsafe(32)


def _post_token(payload: dict[str, str]) -> dict[str, Any]:
    """POST to the OAuth token endpoint (form-urlencoded, not JSON)."""
    resp = requests.post(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=HTTP_TIMEOUT,
    )
    try:
        data = resp.json()
    except ValueError as exc:
        raise TikTokAuthError(f"token endpoint returned non-JSON: {resp.text[:300]}") from exc

    if resp.status_code >= 400 or data.get("error"):
        detail = data.get("error_description") or data.get("error") or data
        raise TikTokAuthError(f"TikTok token request failed: {detail}")
    if not data.get("access_token"):
        raise TikTokAuthError(f"TikTok response without access_token: {data}")
    return data


def _store(token: TikTokToken, data: dict[str, Any]) -> TikTokToken:
    now = timezone.now()
    token.access_token = data["access_token"]
    # A refresh may return a rotated refresh_token; keeping the old one would
    # break the next refresh, so only fall back when the field is absent.
    token.refresh_token = data.get("refresh_token") or token.refresh_token
    token.open_id = data.get("open_id") or token.open_id
    token.scope = data.get("scope") or token.scope
    token.client_key = client_key()
    token.expires_at = now + timezone.timedelta(seconds=int(data.get("expires_in") or 0))
    if data.get("refresh_expires_in"):
        token.refresh_expires_at = now + timezone.timedelta(
            seconds=int(data["refresh_expires_in"])
        )
    token.last_refreshed_at = now
    token.last_error = ""
    token.refresh_fail_count = 0
    token.save()
    return token


def exchange_code(code: str) -> TikTokToken:
    """Exchange an authorization code for the first token pair."""
    if not oauth_configured():
        raise TikTokAuthError("TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET are empty")
    data = _post_token(
        {
            "client_key": client_key(),
            "client_secret": client_secret(),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri(),
        }
    )
    with transaction.atomic():
        token = TikTokToken.load()
        token = _store(token, data)
    logger.info("TikTok OAuth: authorized open_id=%s scope=%s", token.open_id, token.scope)
    return token


def refresh_token(token: TikTokToken | None = None) -> TikTokToken:
    """
    Swap the refresh_token for a fresh access_token.

    On failure the stored tokens are left untouched: a transient 5xx from
    TikTok must not wipe credentials that are still valid.
    """
    if not oauth_configured():
        raise TikTokAuthError("TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET are empty")

    token = token or TikTokToken.load()
    if not token.refresh_token:
        raise TikTokAuthError("No refresh_token stored — run the OAuth flow first")
    if token.refresh_expired:
        raise TikTokAuthError(
            "refresh_token expired (365 days) — the OAuth flow must be repeated"
        )

    # The HTTP call stays outside the transaction: holding a write lock across
    # a network round-trip would stall other writers, and a rollback would also
    # discard the failure bookkeeping below.
    try:
        data = _post_token(
            {
                "client_key": client_key(),
                "client_secret": client_secret(),
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
            }
        )
    except TikTokAuthError as exc:
        token.last_error = str(exc)[:2000]
        token.refresh_fail_count += 1
        token.save(update_fields=["last_error", "refresh_fail_count", "updated_at"])
        raise

    with transaction.atomic():
        token = _store(token, data)

    logger.info("TikTok OAuth: token refreshed, expires_at=%s", token.expires_at)
    _warn_if_reauth_due(token)
    return token


def _warn_if_reauth_due(token: TikTokToken) -> None:
    """Alert once when the yearly re-authorization window gets close."""
    days = token.days_until_reauth
    if days is None or days > TikTokToken.REAUTH_WARNING_DAYS:
        return
    if token.reauth_warned_at and (timezone.now() - token.reauth_warned_at).days < 7:
        return
    try:
        from social.services.comment_notify import notify_staff_text

        notify_staff_text(
            f"⚠️ TikTok: залишилось {days} дн. до кінця дії refresh_token.\n"
            f"Треба заново пройти OAuth в адмінці, інакше автопостинг зупиниться."
        )
    except Exception:
        logger.exception("TikTok reauth warning could not be delivered")
    token.reauth_warned_at = timezone.now()
    token.save(update_fields=["reauth_warned_at", "updated_at"])


def get_valid_access_token() -> str:
    """
    Return a usable access token, refreshing it when it is about to expire.

    Returns an empty string when no token is stored, so callers can fall back
    to the legacy env-var token.
    """
    token = TikTokToken.load()
    if not token.is_authorized:
        return ""

    if token.client_key and token.client_key != client_key():
        raise TikTokAuthError(
            "Stored TikTok token was issued for a different client_key "
            f"({token.client_key[:6]}… vs {client_key()[:6]}…) — "
            "re-run the OAuth flow after switching sandbox/production"
        )

    if token.needs_refresh:
        token = refresh_token(token)
    return token.access_token


def token_status() -> dict[str, Any]:
    token = TikTokToken.load()
    return {
        "authorized": token.is_authorized,
        "sandbox": is_sandbox(),
        "open_id": token.open_id,
        "scope": token.scope,
        "client_key_matches": (not token.client_key) or token.client_key == client_key(),
        "expires_at": token.expires_at,
        "needs_refresh": token.needs_refresh,
        "refresh_expires_at": token.refresh_expires_at,
        "days_until_reauth": token.days_until_reauth,
        "refresh_fail_count": token.refresh_fail_count,
        "last_error": token.last_error,
    }
