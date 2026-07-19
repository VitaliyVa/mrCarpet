"""Keep family orders topic, comments topic, products channel, discussion disjoint."""

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


def orders_thread_id() -> str:
    try:
        from project.models import TelegramSettings

        return _norm(TelegramSettings.load().message_thread_id)
    except Exception:
        return ""


def isolation_issues(
    *,
    channel_id: str = "",
    discussion_id: str = "",
    staff_comments_id: str = "",
    staff_comments_thread_id: str = "",
    family_id: str | None = None,
    orders_thread: str | None = None,
) -> list[str]:
    """Return human-readable conflicts (empty = OK)."""
    channel = _norm(channel_id)
    discussion = _norm(discussion_id)
    staff_chat = _norm(staff_comments_id)
    staff_thread = _norm(staff_comments_thread_id)
    family = _norm(family_id) if family_id is not None else family_chat_id()
    orders_th = _norm(orders_thread) if orders_thread is not None else orders_thread_id()

    issues: list[str] = []

    # Public products targets must never equal staff chats
    for name, value in (
        ("products_channel_id", channel),
        ("products_discussion_chat_id", discussion),
    ):
        if value and family and value == family:
            issues.append(f"{name} must not equal family TelegramSettings.chat_id")
        if value and staff_chat and value == staff_chat:
            issues.append(f"{name} must not equal staff_comments_chat_id")
    if channel and discussion and channel == discussion:
        issues.append(
            "products_channel_id must not equal products_discussion_chat_id"
        )

    # Forum: comments may share family chat_id, but must use a different topic
    effective_staff_chat = staff_chat or family
    if staff_thread and orders_th and staff_thread == orders_th:
        if effective_staff_chat and family and effective_staff_chat == family:
            issues.append(
                "staff_comments_thread_id must not equal orders message_thread_id"
            )
        elif staff_chat and family and staff_chat == family:
            issues.append(
                "staff_comments_thread_id must not equal orders message_thread_id"
            )

    if staff_chat and family and staff_chat == family and not staff_thread:
        issues.append(
            "staff_comments_thread_id required when using family chat "
            "(forum topic «mr.Carpet comments»)"
        )

    return issues


def assert_products_ids_isolated(
    *,
    channel_id: str = "",
    discussion_id: str = "",
    staff_comments_id: str = "",
    staff_comments_thread_id: str = "",
) -> None:
    issues = isolation_issues(
        channel_id=channel_id,
        discussion_id=discussion_id,
        staff_comments_id=staff_comments_id,
        staff_comments_thread_id=staff_comments_thread_id,
    )
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
    staff = _norm(social.staff_comments_chat_id)
    staff_thread = _norm(getattr(social, "staff_comments_thread_id", "") or "")
    family = family_chat_id()
    orders_th = orders_thread_id()
    issues = isolation_issues(
        channel_id=channel,
        discussion_id=discussion,
        staff_comments_id=staff,
        staff_comments_thread_id=staff_thread,
        family_id=family,
        orders_thread=orders_th,
    )
    return {
        "family_chat_id": family or None,
        "orders_thread_id": orders_th or None,
        "products_channel_id": channel or None,
        "products_discussion_chat_id": discussion or None,
        "staff_comments_chat_id": staff or None,
        "staff_comments_thread_id": staff_thread or None,
        "ok": not issues,
        "issues": issues,
    }
