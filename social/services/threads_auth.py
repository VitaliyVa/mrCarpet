"""
Threads OAuth token lifecycle.

Threads is its own OAuth world, not Facebook Login and not the Instagram Graph
API. Three things catch people out, and all three cost a day each:

* **Its own hosts.** Authorization happens on `threads.net`, the API lives on
  `graph.threads.net`. The Meta page access token we already hold is useless
  here.

* **Two app ids in one app.** A Meta app with the Threads use case carries a
  *Threads* App ID and secret alongside the main Meta ones. Using the main
  pair fails with an error that does not mention which id was wrong.

* **No refresh token.** A single 60-day access token is exchanged for a fresh
  60 days using itself, and only once it is at least 24 hours old. A token
  left for 60 days is dead and needs a human in a browser.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

from social.models import ThreadsToken

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://threads.net/oauth/authorize"
GRAPH = "https://graph.threads.net"
TOKEN_URL = f"{GRAPH}/oauth/access_token"
EXCHANGE_URL = f"{GRAPH}/access_token"
REFRESH_URL = f"{GRAPH}/refresh_access_token"
HTTP_TIMEOUT = 30

# threads_basic is required by every endpoint; threads_content_publish is what
# lets us post at all.
#
# The reply scopes are requested now even though nothing reads comments yet:
# adding a scope later means dragging a human back through the consent screen
# in a browser, and the whole point of the format is that people answer the
# question in the replies. Cheaper to ask once.
SCOPES = (
    "threads_basic",
    "threads_content_publish",
    "threads_read_replies",
    "threads_manage_replies",
)


class ThreadsAuthError(RuntimeError):
    pass


def app_id() -> str:
    """The *Threads* app id, not the Meta one — they differ inside one app."""
    return (getattr(settings, "THREADS_APP_ID", "") or "").strip()


def app_secret() -> str:
    return (getattr(settings, "THREADS_APP_SECRET", "") or "").strip()


def redirect_uri() -> str:
    configured = (getattr(settings, "THREADS_REDIRECT_URI", "") or "").strip()
    return configured or "https://mrcarpet24.com/api/threads/callback/"


def oauth_configured() -> bool:
    return bool(app_id() and app_secret())


def new_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorize_url(state: str) -> str:
    if not oauth_configured():
        raise ThreadsAuthError("THREADS_APP_ID / THREADS_APP_SECRET are empty")
    params = {
        "client_id": app_id(),
        "redirect_uri": redirect_uri(),
        "scope": ",".join(SCOPES),
        "response_type": "code",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _get(url: str, params: dict[str, str]) -> dict[str, Any]:
    try:
        resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise ThreadsAuthError(f"Threads HTTP error: {exc}") from exc
    return _payload(resp)


def _payload(resp) -> dict[str, Any]:
    try:
        data = resp.json() if resp.content else {}
    except ValueError as exc:
        raise ThreadsAuthError(f"Threads returned non-JSON: {resp.text[:300]}") from exc
    if resp.status_code >= 400 or data.get("error"):
        err = data.get("error") or data
        raise ThreadsAuthError(f"Threads API {resp.status_code}: {err}")
    if not data.get("access_token"):
        raise ThreadsAuthError(f"Threads response without access_token: {data}")
    return data


def _store(token: ThreadsToken, data: dict[str, Any], *, refreshed: bool) -> ThreadsToken:
    now = timezone.now()
    token.access_token = data["access_token"]
    if data.get("user_id"):
        token.user_id = str(data["user_id"])
    seconds = int(data.get("expires_in") or 0)
    if seconds:
        token.expires_at = now + timezone.timedelta(seconds=seconds)
    if refreshed:
        token.last_refreshed_at = now
    else:
        token.issued_at = now
        token.last_refreshed_at = None
    token.scope = ",".join(SCOPES)
    token.last_error = ""
    token.refresh_fail_count = 0
    token.save()
    return token


def exchange_code(code: str) -> ThreadsToken:
    """
    Authorization code -> short-lived token -> 60-day long-lived token.

    The short-lived token lasts an hour and is useless for a scheduler, so the
    exchange happens immediately rather than being left for later.
    """
    if not oauth_configured():
        raise ThreadsAuthError("THREADS_APP_ID / THREADS_APP_SECRET are empty")

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "client_id": app_id(),
                "client_secret": app_secret(),
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri(),
                "code": code,
            },
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ThreadsAuthError(f"Threads HTTP error: {exc}") from exc
    short = _payload(resp)

    long_lived = _get(
        EXCHANGE_URL,
        {
            "grant_type": "th_exchange_token",
            "client_secret": app_secret(),
            "access_token": short["access_token"],
        },
    )
    # user_id only comes back on the first call, so carry it across.
    long_lived.setdefault("user_id", short.get("user_id"))

    token = _store(ThreadsToken.load(), long_lived, refreshed=False)
    _fetch_profile(token)
    logger.info("Threads OAuth: authorized user_id=%s", token.user_id)
    return token


def refresh_token(token: ThreadsToken | None = None) -> ThreadsToken:
    """
    Trade the current token for another 60 days.

    Refuses when the token is younger than 24 hours, because Meta would reject
    it anyway and a rejection here would look like a credentials problem.
    """
    if not oauth_configured():
        raise ThreadsAuthError("THREADS_APP_ID / THREADS_APP_SECRET are empty")

    token = token or ThreadsToken.load()
    if not token.access_token:
        raise ThreadsAuthError("No Threads token stored — run the OAuth flow first")
    if token.expired:
        raise ThreadsAuthError(
            "Threads token expired (60 days) — the OAuth flow must be repeated"
        )
    if not token.old_enough_to_refresh:
        raise ThreadsAuthError(
            "Threads refuses to refresh a token younger than 24h — try tomorrow"
        )

    try:
        data = _get(
            REFRESH_URL,
            {
                "grant_type": "th_refresh_token",
                "access_token": token.access_token,
            },
        )
    except ThreadsAuthError as exc:
        token.last_error = str(exc)[:2000]
        token.refresh_fail_count += 1
        token.save(update_fields=["last_error", "refresh_fail_count", "updated_at"])
        raise

    token = _store(token, data, refreshed=True)
    logger.info("Threads OAuth: token refreshed, expires_at=%s", token.expires_at)
    _warn_if_reauth_due(token)
    return token


def _fetch_profile(token: ThreadsToken) -> None:
    """Best-effort username, so the admin shows which account is connected."""
    try:
        resp = requests.get(
            f"{GRAPH}/v1.0/me",
            params={"fields": "id,username", "access_token": token.access_token},
            timeout=HTTP_TIMEOUT,
        )
        data = resp.json() if resp.content else {}
    except Exception:
        logger.info("Threads profile fetch failed")
        return
    if data.get("username"):
        token.username = str(data["username"])[:190]
    if data.get("id") and not token.user_id:
        token.user_id = str(data["id"])
    token.save(update_fields=["username", "user_id", "updated_at"])


def _warn_if_reauth_due(token: ThreadsToken) -> None:
    days = token.days_until_expiry
    if days is None or days > ThreadsToken.REAUTH_WARNING_DAYS:
        return
    if token.reauth_warned_at and (timezone.now() - token.reauth_warned_at).days < 2:
        return
    try:
        from social.services.comment_notify import notify_staff_text

        notify_staff_text(
            f"⚠️ Threads: залишилось {days} дн. до кінця дії токена.\n"
            f"Треба заново пройти OAuth в адмінці, інакше пости в Threads зупиняться.",
            video=True,
        )
    except Exception:
        logger.exception("Threads reauth warning could not be delivered")
    token.reauth_warned_at = timezone.now()
    token.save(update_fields=["reauth_warned_at", "updated_at"])


def get_valid_access_token() -> str:
    """
    A usable token, refreshed when it is getting old enough to worry about.

    Returns "" when nothing is stored so callers can report "not configured"
    rather than crash.
    """
    token = ThreadsToken.load()
    if not token.is_authorized:
        return ""
    if token.expired:
        return ""
    if token.needs_refresh and token.old_enough_to_refresh:
        try:
            token = refresh_token(token)
        except ThreadsAuthError:
            # Still valid for now; the warning above will chase a human.
            logger.warning("Threads refresh failed, using the existing token")
    return token.access_token


def token_status() -> dict[str, Any]:
    token = ThreadsToken.load()
    return {
        "authorized": token.is_authorized,
        "user_id": token.user_id,
        "username": token.username,
        "expires_at": token.expires_at,
        "days_until_expiry": token.days_until_expiry,
        "needs_refresh": token.needs_refresh,
        "can_refresh_now": token.old_enough_to_refresh,
        "refresh_fail_count": token.refresh_fail_count,
        "last_error": token.last_error,
    }
