"""Sliding-window chat memory."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from project.models import TelegramChatMemory, TelegramChatMessage

WINDOW = 12
SUMMARY_EVERY = 20
RETENTION_DAYS = 7


def _thread_key(thread_id) -> str:
    if thread_id in (None, ""):
        return ""
    return str(thread_id)


def append_message(chat_id, thread_id, role, content, tg_user_id=None):
    TelegramChatMessage.objects.create(
        chat_id=str(chat_id),
        thread_id=_thread_key(thread_id),
        role=role,
        content=(content or "")[:8000],
        tg_user_id=tg_user_id,
    )
    _cleanup_old(chat_id, thread_id)


def get_memory_context(chat_id, thread_id) -> tuple[str, list[dict]]:
    chat_id = str(chat_id)
    thread_id = _thread_key(thread_id)
    mem, _ = TelegramChatMemory.objects.get_or_create(
        chat_id=chat_id, thread_id=thread_id
    )
    rows = list(
        TelegramChatMessage.objects.filter(chat_id=chat_id, thread_id=thread_id)
        .order_by("-created")[:WINDOW]
    )
    rows.reverse()
    history = [{"role": r.role, "content": r.content} for r in rows]
    return mem.summary or "", history


def maybe_update_summary(chat_id, thread_id, summarize_fn):
    """Call summarize_fn(summary, recent_texts) -> new_summary occasionally."""
    chat_id = str(chat_id)
    thread_id = _thread_key(thread_id)
    total = TelegramChatMessage.objects.filter(
        chat_id=chat_id, thread_id=thread_id
    ).count()
    if total == 0 or total % SUMMARY_EVERY != 0:
        return
    mem, _ = TelegramChatMemory.objects.get_or_create(
        chat_id=chat_id, thread_id=thread_id
    )
    recent = list(
        TelegramChatMessage.objects.filter(chat_id=chat_id, thread_id=thread_id)
        .order_by("-created")[:WINDOW]
        .values_list("role", "content")
    )
    recent.reverse()
    blob = "\n".join(f"{r}: {c}" for r, c in recent)
    try:
        new_summary = summarize_fn(mem.summary or "", blob)
    except Exception:
        return
    if new_summary:
        mem.summary = new_summary[:2000]
        mem.save(update_fields=["summary", "updated"])


def user_rate_exceeded(tg_user_id, limit: int) -> bool:
    if not tg_user_id or not limit:
        return False
    since = timezone.now() - timedelta(minutes=10)
    count = TelegramChatMessage.objects.filter(
        tg_user_id=tg_user_id,
        role=TelegramChatMessage.ROLE_USER,
        created__gte=since,
    ).count()
    return count >= limit


def _cleanup_old(chat_id, thread_id):
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    TelegramChatMessage.objects.filter(
        chat_id=str(chat_id),
        thread_id=_thread_key(thread_id),
        created__lt=cutoff,
    ).delete()
