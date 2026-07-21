"""
Threads OAuth flow — staff-only.

Staff-gated for the same reason as the TikTok flow: the callback writes the
token the daily poster runs on, so an open endpoint would let anyone bind
their own Threads account to the store.

Repeated at most once every 60 days, and only if the background refresh has
been failing — a healthy token renews itself.
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.html import escape

from social.services.threads_auth import (
    ThreadsAuthError,
    build_authorize_url,
    exchange_code,
    new_state,
    oauth_configured,
    redirect_uri,
)

logger = logging.getLogger(__name__)

STATE_SESSION_KEY = "threads_oauth_state"


def _page(title: str, body: str, status: int = 200) -> HttpResponse:
    return HttpResponse(
        f"<!doctype html><meta charset='utf-8'>"
        f"<title>{escape(title)}</title>"
        f"<div style=\"font-family:system-ui,sans-serif;max-width:640px;"
        f"margin:60px auto;line-height:1.6\">{body}</div>",
        status=status,
    )


@staff_member_required
def threads_oauth_start(request):
    if not oauth_configured():
        return _page(
            "Threads OAuth",
            "<h2>Не налаштовано</h2><p>Порожні <code>THREADS_APP_ID</code> "
            "або <code>THREADS_APP_SECRET</code> у .env.</p>"
            "<p>Увага: це <b>Threads</b> App ID, не основний Meta App ID — "
            "у застосунку з Threads use case їх два.</p>",
            status=400,
        )

    state = new_state()
    request.session[STATE_SESSION_KEY] = state
    return HttpResponseRedirect(build_authorize_url(state))


@staff_member_required
def threads_oauth_callback(request):
    error = request.GET.get("error") or ""
    if error:
        description = request.GET.get("error_description") or ""
        logger.warning("Threads OAuth denied: %s %s", error, description)
        return _page(
            "Threads OAuth",
            f"<h2>Авторизацію не завершено</h2><p>{escape(error)} "
            f"{escape(description)}</p>",
            status=400,
        )

    expected = request.session.pop(STATE_SESSION_KEY, "")
    received = request.GET.get("state") or ""
    if not expected or received != expected:
        logger.warning("Threads OAuth state mismatch")
        return _page(
            "Threads OAuth",
            "<h2>Неправильний state</h2><p>Почни авторизацію заново з адмінки — "
            "посилання одноразове.</p>",
            status=400,
        )

    code = request.GET.get("code") or ""
    if not code:
        return _page("Threads OAuth", "<h2>Немає code у відповіді</h2>", status=400)

    try:
        token = exchange_code(code)
    except ThreadsAuthError as exc:
        logger.exception("Threads OAuth exchange failed")
        return _page(
            "Threads OAuth",
            f"<h2>Обмін коду не вдався</h2><p>{escape(str(exc))}</p>"
            "<p>Якщо це повторне відкриття сторінки — code вже використаний, "
            "почни заново.</p>",
            status=400,
        )

    expires = f"{token.expires_at:%Y-%m-%d}" if token.expires_at else "?"
    return _page(
        "Threads OAuth",
        f"<h2>Готово</h2>"
        f"<p>Акаунт: <b>@{escape(token.username or '?')}</b><br>"
        f"user_id: <code>{escape(token.user_id)}</code><br>"
        f"scope: <code>{escape(token.scope)}</code><br>"
        f"токен діє до: <b>{expires}</b> (оновлюється сам)</p>"
        f"<p>redirect_uri: <code>{escape(redirect_uri())}</code></p>"
        f"<p><a href='/admin/social/threadstoken/'>← до адмінки</a></p>",
    )
