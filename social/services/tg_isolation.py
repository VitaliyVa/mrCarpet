"""Keep family orders chat, products channel, and discussion IDs disjoint."""

from __future__ import annotations

from typing import Any


def _norm(value: str | None) -> str:
    return (value or "").strip()


def family_chat_id() -> str:
    try:
        from project.models import TelegramSettings

        return _norm(TelegramSettings.load().chat_id)
    except Exception:
        return ""


def isolation_issues(
    *,
    channel_id: str = "",
    discussion_id: str = "",
    family_id: str | None = None,
) -> list[str]:
    """Return human-readable conflicts (empty = OK)."""
    channel = _norm(channel_id)
    discussion = _norm(discussion_id)
    family = _norm(family_id) if family_id is not None else family_chat_id()
    issues: list[str] = []
    if channel and family and channel == family:
        issues.append(
            "products_channel_id must not equal family TelegramSettings.chat_id"
        )
    if discussion and family and discussion == family:
        issues.append(
            "products_discussion_chat_id must not equal family TelegramSettings.chat_id"
        )
    if channel and discussion and channel == discussion:
        issues.append(
            "products_channel_id must not equal products_discussion_chat_id"
        )
    return issues


def assert_products_ids_isolated(
    *,
    channel_id: str = "",
    discussion_id: str = "",
) -> None:
    issues = isolation_issues(channel_id=channel_id, discussion_id=discussion_id)
    if issues:
        raise ValueError("; ".join(issues))


def is_products_discussion_chat(chat_id: Any) -> bool:
    """True when update chat is the configured products discussion group."""
    from social.models import SocialSettings

    discussion = _norm(SocialSettings.load().products_discussion_chat_id)
    if not discussion:
        return False
    return str(chat_id or "").strip() == discussion


def isolation_status() -> dict[str, Any]:
    from social.models import SocialSettings

    social = SocialSettings.load()
    channel = _norm(social.products_channel_id)
    discussion = _norm(social.products_discussion_chat_id)
    family = family_chat_id()
    issues = isolation_issues(
        channel_id=channel, discussion_id=discussion, family_id=family
    )
    return {
        "family_chat_id": family or None,
        "products_channel_id": channel or None,
        "products_discussion_chat_id": discussion or None,
        "ok": not issues,
        "issues": issues,
    }
