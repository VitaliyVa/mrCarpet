"""
One place that knows whether every credential is still alive.

Four networks, four expiry models, and no two alike:

* **TikTok** — access token 24h, refresh token 365 days from the *initial*
  grant. Not rolling: it dies on a fixed date no matter how often we use it.
* **Meta** (IG + FB) — a long-lived page token with no scheduled expiry, but
  revocable at any time and silently invalidated by a password change.
* **Threads** — 60 days, renewed by itself, and refusing to renew during the
  first 24 hours.
* **Google** — access token 1h, refresh token effectively permanent *unless*
  the Cloud app sits in Testing, where it expires weekly.

A dead token does not announce itself. The daily run simply stops posting to
one network, the report shows a failure nobody reads twice, and the loss is
noticed weeks later as "why are there no Reels lately". This module turns
that silence into one message a day.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Below this, start saying so every day rather than only when it breaks.
WARN_DAYS = 14


@dataclass
class TokenState:
    network: str
    ok: bool
    detail: str
    days_left: int | None = None
    action: str = ""
    #: True when a human has to do something in a browser — the kind of
    #: failure no amount of retrying will fix.
    needs_human: bool = False


@dataclass
class HealthReport:
    states: list[TokenState] = field(default_factory=list)

    @property
    def problems(self) -> list[TokenState]:
        return [s for s in self.states if not s.ok]

    @property
    def warnings(self) -> list[TokenState]:
        return [
            s
            for s in self.states
            if s.ok and s.days_left is not None and s.days_left <= WARN_DAYS
        ]

    @property
    def healthy(self) -> bool:
        return not self.problems and not self.warnings


def _tiktok() -> TokenState:
    from social.models import TikTokToken

    token = TikTokToken.load()
    if not token.is_authorized:
        return TokenState(
            "TikTok", False, "не авторизовано",
            action="Social → TikTok token → авторизувати", needs_human=True,
        )
    days = token.days_until_reauth
    if token.refresh_expired:
        return TokenState(
            "TikTok", False, "refresh_token протух (365 днів)",
            days_left=0, action="заново пройти OAuth", needs_human=True,
        )
    if token.refresh_fail_count >= 3:
        return TokenState(
            "TikTok", False,
            f"{token.refresh_fail_count} невдалих оновлень поспіль",
            days_left=days, action="перевірити last_error в адмінці",
        )
    return TokenState("TikTok", True, "живий", days_left=days)


def _meta() -> TokenState:
    """
    Meta page tokens carry no expiry date, so the only honest check is to use
    one. Cheap call, and it fails exactly the way a revoked token would.
    """
    from social.services import meta

    if not meta.meta_configured(need_ig=True, need_fb=True):
        return TokenState(
            "Meta (IG/FB)", False, "не налаштовано (META_* порожні)",
            action="перевірити .env на проді", needs_human=True,
        )
    try:
        meta._graph("GET", "me", params={"fields": "id"})
    except Exception as exc:
        return TokenState(
            "Meta (IG/FB)", False, f"токен не працює: {str(exc)[:120]}",
            action="перевипустити META_PAGE_ACCESS_TOKEN", needs_human=True,
        )
    return TokenState("Meta (IG/FB)", True, "живий")


def _threads() -> TokenState:
    from social.models import ThreadsToken

    token = ThreadsToken.load()
    if not token.is_authorized:
        return TokenState(
            "Threads", False, "не авторизовано",
            action="Social → Threads token → авторизувати", needs_human=True,
        )
    if token.expired:
        return TokenState(
            "Threads", False, "токен протух (60 днів)", days_left=0,
            action="заново пройти OAuth", needs_human=True,
        )
    days = token.days_until_expiry
    if token.refresh_fail_count >= 3:
        return TokenState(
            "Threads", False,
            f"{token.refresh_fail_count} невдалих оновлень поспіль",
            days_left=days, action="перевірити last_error в адмінці",
        )
    return TokenState("Threads", True, "живий", days_left=days)


def _youtube() -> TokenState:
    from social.models import YouTubeToken
    from social.services.youtube_auth import YouTubeAuthError, get_valid_access_token

    token = YouTubeToken.load()
    if not token.is_authorized:
        return TokenState(
            "YouTube", False, "не авторизовано",
            action="Social → YouTube token → авторизувати", needs_human=True,
        )
    # No expiry date to read: a Google refresh token either works or is gone.
    # Refreshing is the only way to find out, and it costs one call.
    try:
        if not get_valid_access_token():
            raise YouTubeAuthError("порожній токен")
    except Exception as exc:
        detail = str(exc)[:140]
        hint = (
            "застосунок у Google Cloud лишився в Testing — там refresh_token "
            "живе 7 днів; перевір Publishing status"
            if "invalid_grant" in detail
            else "перевірити last_error в адмінці"
        )
        return TokenState(
            "YouTube", False, f"токен не оновлюється: {detail}",
            action=hint, needs_human=True,
        )
    return TokenState("YouTube", True, "живий")


def _checks():
    """
    Resolved on each call rather than captured at import.

    A tuple of function objects built at module level cannot be patched by
    name, which makes the "one broken check must not hide the others"
    behaviour untestable — and that behaviour is the whole point.
    """
    return (_tiktok, _meta, _threads, _youtube)


def check_all() -> HealthReport:
    """Run every check. One broken network must not hide the others."""
    report = HealthReport()
    for check in _checks():
        try:
            report.states.append(check())
        except Exception as exc:
            logger.exception("token health check crashed")
            # getattr, not check.__name__: the handler must not be able to
            # raise. The one guarantee this loop makes is that a single broken
            # check cannot hide the other three.
            name = getattr(check, "__name__", "") or "перевірка"
            report.states.append(
                TokenState(
                    name.strip("_"), False, f"перевірка впала: {str(exc)[:120]}"
                )
            )
    return report


def format_report(report: HealthReport) -> str:
    if report.healthy:
        lines = ["🔑 Токени: усі живі"]
    elif report.problems:
        lines = ["🔴 Токени: є проблеми"]
    else:
        lines = ["🟡 Токени: скоро треба буде продовжити"]

    lines.append("")
    for state in report.states:
        mark = "✅" if state.ok else "❌"
        if state.ok and state.days_left is not None and state.days_left <= WARN_DAYS:
            mark = "⚠️"
        tail = f" · {state.days_left} дн." if state.days_left is not None else ""
        lines.append(f"{mark} {state.network} — {state.detail}{tail}")
        if state.action:
            lines.append(f"   ↳ {state.action}")

    if any(s.needs_human for s in report.problems):
        lines += ["", "Автоматично це не полагодиться — потрібні руки."]
    return "\n".join(lines)


def run_and_report(*, always: bool = False) -> HealthReport:
    """
    Check everything and message the video topic when it matters.

    Silent on a healthy day by default: a daily "all fine" trains people to
    ignore the channel, and this message has to be worth reading the one time
    it is not fine.
    """
    report = check_all()
    if report.healthy and not always:
        logger.info("token health: all good, staying quiet")
        return report

    try:
        from social.services.comment_notify import notify_staff_text

        notify_staff_text(format_report(report), video=True)
    except Exception:
        logger.exception("token health report could not be delivered")
    return report
