"""
YouTube (Google) OAuth token lifecycle.

Standard Google OAuth: a one-hour access_token refreshed from a long-lived
refresh_token. Two details decide whether this survives unattended.

`access_type=offline` plus `prompt=consent` on the authorize URL — without
both, Google returns no refresh_token at all on a repeat authorization, and
the integration works for exactly one hour before dying in a way that looks
like a server problem.

The Cloud app must be **published**, not in Testing: Google expires refresh
tokens of testing apps after seven days. See social/YOUTUBE_SETUP.md.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

from social.models import YouTubeToken

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3"
HTTP_TIMEOUT = 30

# Exactly one scope. youtube.upload is enough to publish and nothing more —
# a narrower request is both safer and easier to get through review.
SCOPES = ("https://www.googleapis.com/auth/youtube.upload",)


class YouTubeAuthError(RuntimeError):
    pass


def client_id() -> str:
    return (getattr(settings, "YOUTUBE_CLIENT_ID", "") or "").strip()


def client_secret() -> str:
    return (getattr(settings, "YOUTUBE_CLIENT_SECRET", "") or "").strip()


def redirect_uri() -> str:
    configured = (getattr(settings, "YOUTUBE_REDIRECT_URI", "") or "").strip()
    return configured or "https://mrcarpet24.com/api/youtube/callback/"


def oauth_configured() -> bool:
    return bool(client_id() and client_secret())


def new_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorize_url(state: str) -> str:
    if not oauth_configured():
        raise YouTubeAuthError("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET are empty")
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        # Both are required to be handed a refresh_token. Google silently
        # omits it otherwise, and the failure surfaces an hour later.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _post_token(payload: dict[str, str]) -> dict[str, Any]:
    try:
        resp = requests.post(TOKEN_URL, data=payload, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise YouTubeAuthError(f"Google HTTP error: {exc}") from exc

    try:
        data = resp.json() if resp.content else {}
    except ValueError as exc:
        raise YouTubeAuthError(f"Google returned non-JSON: {resp.text[:300]}") from exc

    if resp.status_code >= 400 or data.get("error"):
        detail = data.get("error_description") or data.get("error") or data
        raise YouTubeAuthError(f"Google token request failed: {detail}")
    if not data.get("access_token"):
        raise YouTubeAuthError(f"Google response without access_token: {data}")
    return data


def _store(token: YouTubeToken, data: dict[str, Any], *, first: bool) -> YouTubeToken:
    now = timezone.now()
    token.access_token = data["access_token"]
    # A refresh response carries no refresh_token; keeping the stored one is
    # the whole point. Overwriting with "" here would end the integration.
    if data.get("refresh_token"):
        token.refresh_token = data["refresh_token"]
    if data.get("scope"):
        token.scope = data["scope"][:255]
    token.expires_at = now + timezone.timedelta(seconds=int(data.get("expires_in") or 3600))
    if first:
        token.authorized_at = now
    else:
        token.last_refreshed_at = now
    token.last_error = ""
    token.refresh_fail_count = 0
    token.save()
    return token


def exchange_code(code: str) -> YouTubeToken:
    if not oauth_configured():
        raise YouTubeAuthError("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET are empty")

    data = _post_token(
        {
            "code": code,
            "client_id": client_id(),
            "client_secret": client_secret(),
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        }
    )
    if not data.get("refresh_token"):
        raise YouTubeAuthError(
            "Google returned no refresh_token — the app is likely missing "
            "access_type=offline / prompt=consent, or this account already "
            "granted access. Revoke it and authorize again."
        )

    token = _store(YouTubeToken.load(), data, first=True)
    _fetch_channel(token)
    logger.info("YouTube OAuth: authorized channel=%s", token.channel_title)
    return token


def refresh_token(token: YouTubeToken | None = None) -> YouTubeToken:
    if not oauth_configured():
        raise YouTubeAuthError("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET are empty")

    token = token or YouTubeToken.load()
    if not token.refresh_token:
        raise YouTubeAuthError("No refresh_token stored — run the OAuth flow first")

    try:
        data = _post_token(
            {
                "refresh_token": token.refresh_token,
                "client_id": client_id(),
                "client_secret": client_secret(),
                "grant_type": "refresh_token",
            }
        )
    except YouTubeAuthError as exc:
        token.last_error = str(exc)[:2000]
        token.refresh_fail_count += 1
        token.save(update_fields=["last_error", "refresh_fail_count", "updated_at"])
        _warn_if_dead(token, str(exc))
        raise

    token = _store(token, data, first=False)
    logger.info("YouTube OAuth: token refreshed, expires_at=%s", token.expires_at)
    return token


def _warn_if_dead(token: YouTubeToken, error: str) -> None:
    """
    Chase a human once the failures stop looking transient.

    `invalid_grant` means the refresh_token is gone for good — revoked, or
    expired because the Cloud app is still in Testing mode.
    """
    if "invalid_grant" not in error and token.refresh_fail_count < 3:
        return
    try:
        from social.services.comment_notify import notify_staff_text

        notify_staff_text(
            "⚠️ YouTube: токен більше не оновлюється.\n"
            f"Помилка: {error[:300]}\n"
            "Найчастіша причина — застосунок у Google Cloud лишився в статусі "
            "Testing (там refresh_token живе 7 днів). Перевір Publishing status, "
            "потім заново пройди OAuth в адмінці.",
            video=True,
        )
    except Exception:
        logger.exception("YouTube token alert could not be delivered")


def _fetch_channel(token: YouTubeToken) -> None:
    """
    Record which channel we are actually attached to.

    Best-effort: youtube.upload alone may not grant channels.list, and failing
    to learn the title must not undo a successful authorization.
    """
    try:
        resp = requests.get(
            f"{API}/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {token.access_token}"},
            timeout=HTTP_TIMEOUT,
        )
        items = (resp.json() or {}).get("items") or []
    except Exception:
        logger.info("YouTube channel lookup failed")
        return
    if not items:
        return
    item = items[0]
    token.channel_id = str(item.get("id") or "")[:128]
    token.channel_title = str((item.get("snippet") or {}).get("title") or "")[:190]
    token.save(update_fields=["channel_id", "channel_title", "updated_at"])


def get_valid_access_token() -> str:
    token = YouTubeToken.load()
    if not token.is_authorized:
        return ""
    if token.needs_refresh:
        token = refresh_token(token)
    return token.access_token


def token_status() -> dict[str, Any]:
    token = YouTubeToken.load()
    return {
        "authorized": token.is_authorized,
        "channel_id": token.channel_id,
        "channel_title": token.channel_title,
        "scope": token.scope,
        "expires_at": token.expires_at,
        "needs_refresh": token.needs_refresh,
        "refresh_fail_count": token.refresh_fail_count,
        "last_error": token.last_error,
        "oauth_configured": oauth_configured(),
    }
