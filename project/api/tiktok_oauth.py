"""
TikTok Login Kit OAuth flow — staff-only.

Both views are staff-gated on purpose: the callback writes the tokens the
daily poster runs on, so an open endpoint would let anyone bind their own
TikTok account to the store.

The access token expires after 24h and is refreshed in the background; this
flow only has to be repeated when the 365-day refresh_token runs out.
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.html import escape

from social.services.tiktok_auth import (
    TikTokAuthError,
    build_authorize_url,
    exchange_code,
    is_sandbox,
    new_state,
    oauth_configured,
    redirect_uri,
)

logger = logging.getLogger(__name__)

STATE_SESSION_KEY = "tiktok_oauth_state"


def _page(title: str, body: str, status: int = 200) -> HttpResponse:
    return HttpResponse(
        f"<!doctype html><meta charset='utf-8'>"
        f"<title>{escape(title)}</title>"
        f"<div style=\"font-family:system-ui,sans-serif;max-width:640px;"
        f"margin:60px auto;line-height:1.6\">{body}</div>",
        status=status,
    )


@staff_member_required
def tiktok_oauth_start(request):
    """Redirect the operator to TikTok's consent screen."""
    if not oauth_configured():
        return _page(
            "TikTok OAuth",
            "<h2>Не налаштовано</h2><p>Порожні <code>TIKTOK_CLIENT_KEY</code> "
            "або <code>TIKTOK_CLIENT_SECRET</code> у .env.</p>",
            status=400,
        )

    state = new_state()
    request.session[STATE_SESSION_KEY] = state
    return HttpResponseRedirect(build_authorize_url(state))


@staff_member_required
def tiktok_oauth_callback(request):
    """Validate state, trade the code for tokens, store them."""
    error = request.GET.get("error") or ""
    if error:
        description = request.GET.get("error_description") or ""
        logger.warning("TikTok OAuth denied: %s %s", error, description)
        return _page(
            "TikTok OAuth",
            f"<h2>Авторизацію не завершено</h2><p>{escape(error)} "
            f"{escape(description)}</p>",
            status=400,
        )

    expected = request.session.pop(STATE_SESSION_KEY, "")
    received = request.GET.get("state") or ""
    if not expected or received != expected:
        logger.warning("TikTok OAuth state mismatch")
        return _page(
            "TikTok OAuth",
            "<h2>Неправильний state</h2><p>Почни авторизацію заново з адмінки — "
            "посилання одноразове.</p>",
            status=400,
        )

    code = request.GET.get("code") or ""
    if not code:
        return _page(
            "TikTok OAuth", "<h2>Немає code у відповіді</h2>", status=400
        )

    try:
        token = exchange_code(code)
    except TikTokAuthError as exc:
        logger.exception("TikTok OAuth exchange failed")
        return _page(
            "TikTok OAuth",
            f"<h2>Обмін коду не вдався</h2><p>{escape(str(exc))}</p>"
            "<p>Якщо це повторне відкриття сторінки — code вже використаний, "
            "почни заново.</p>",
            status=400,
        )

    env = "Sandbox" if is_sandbox() else "Production"
    return _page(
        "TikTok OAuth",
        f"<h2>Готово</h2>"
        f"<p>Середовище: <b>{env}</b><br>"
        f"open_id: <code>{escape(token.open_id)}</code><br>"
        f"scope: <code>{escape(token.scope)}</code><br>"
        f"access_token діє до: <b>{token.expires_at:%Y-%m-%d %H:%M}</b><br>"
        f"переавторизація потрібна до: "
        f"<b>{token.refresh_expires_at:%Y-%m-%d}</b></p>"
        f"<p>redirect_uri: <code>{escape(redirect_uri())}</code></p>"
        f"<p><a href='/admin/social/tiktoktoken/'>← до адмінки</a></p>",
    )
