"""
YouTube (Google) OAuth flow — staff-only.

Staff-gated for the same reason as the TikTok and Threads flows: the callback
writes the credentials the daily uploader runs on.

Expect an "Google hasn't verified this app" interstitial on the consent
screen. That is the app being published but unverified, which is fine for a
single owner account — verification only removes the warning for strangers.
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.html import escape

from social.services.youtube_auth import (
    YouTubeAuthError,
    build_authorize_url,
    exchange_code,
    new_state,
    oauth_configured,
    redirect_uri,
)

logger = logging.getLogger(__name__)

STATE_SESSION_KEY = "youtube_oauth_state"


def _page(title: str, body: str, status: int = 200) -> HttpResponse:
    return HttpResponse(
        f"<!doctype html><meta charset='utf-8'>"
        f"<title>{escape(title)}</title>"
        f"<div style=\"font-family:system-ui,sans-serif;max-width:640px;"
        f"margin:60px auto;line-height:1.6\">{body}</div>",
        status=status,
    )


@staff_member_required
def youtube_oauth_start(request):
    if not oauth_configured():
        return _page(
            "YouTube OAuth",
            "<h2>Не налаштовано</h2><p>Порожні <code>YOUTUBE_CLIENT_ID</code> "
            "або <code>YOUTUBE_CLIENT_SECRET</code> у .env.</p>",
            status=400,
        )

    state = new_state()
    request.session[STATE_SESSION_KEY] = state
    return HttpResponseRedirect(build_authorize_url(state))


@staff_member_required
def youtube_oauth_callback(request):
    error = request.GET.get("error") or ""
    if error:
        logger.warning("YouTube OAuth denied: %s", error)
        return _page(
            "YouTube OAuth",
            f"<h2>Авторизацію не завершено</h2><p>{escape(error)}</p>",
            status=400,
        )

    expected = request.session.pop(STATE_SESSION_KEY, "")
    received = request.GET.get("state") or ""
    if not expected or received != expected:
        logger.warning("YouTube OAuth state mismatch")
        return _page(
            "YouTube OAuth",
            "<h2>Неправильний state</h2><p>Почни авторизацію заново з адмінки — "
            "посилання одноразове.</p>",
            status=400,
        )

    code = request.GET.get("code") or ""
    if not code:
        return _page("YouTube OAuth", "<h2>Немає code у відповіді</h2>", status=400)

    try:
        token = exchange_code(code)
    except YouTubeAuthError as exc:
        logger.exception("YouTube OAuth exchange failed")
        return _page(
            "YouTube OAuth",
            f"<h2>Обмін коду не вдався</h2><p>{escape(str(exc))}</p>"
            "<p>Якщо Google не віддав refresh_token — відклич доступ на "
            "<a href='https://myaccount.google.com/permissions'>сторінці дозволів</a> "
            "і спробуй ще раз.</p>",
            status=400,
        )

    channel = token.channel_title or token.channel_id or "(не визначено)"
    return _page(
        "YouTube OAuth",
        f"<h2>Готово</h2>"
        f"<p>Канал: <b>{escape(channel)}</b><br>"
        f"channel_id: <code>{escape(token.channel_id or '—')}</code><br>"
        f"scope: <code>{escape(token.scope)}</code></p>"
        f"<p>redirect_uri: <code>{escape(redirect_uri())}</code></p>"
        "<p><b>Увага:</b> поки не пройдено YouTube API compliance audit, "
        "кожне завантаження мовчки стає приватним. Це очікувано.</p>"
        f"<p><a href='/admin/social/youtubetoken/'>← до адмінки</a></p>",
    )
