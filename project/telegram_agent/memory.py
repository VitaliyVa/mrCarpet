"""Sliding-window chat memory with hard caps (no prompt overflow)."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from project.models import TelegramChatMemory, TelegramChatMessage

WINDOW = 12  # turns fed into LLM prompt
DB_KEEP = 40  # rows kept in DB per chat+thread (hard trim)
SUMMARY_EVERY = 20
RETENTION_DAYS = 7
MAX_HISTORY_CHARS = 6000  # soft cap for prompt history blob
MAX_SUMMARY_CHARS = 2000


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
    _trim_overflow(chat_id, thread_id)
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
    history = _cap_history_chars(history)
    summary = (mem.summary or "")[:MAX_SUMMARY_CHARS]
    return summary, history


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
        mem.summary = new_summary[:MAX_SUMMARY_CHARS]
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


def memory_stats(chat_id, thread_id) -> dict:
    chat_id = str(chat_id)
    thread_id = _thread_key(thread_id)
    total = TelegramChatMessage.objects.filter(
        chat_id=chat_id, thread_id=thread_id
    ).count()
    mem = TelegramChatMemory.objects.filter(
        chat_id=chat_id, thread_id=thread_id
    ).first()
    summary, history = get_memory_context(chat_id, thread_id)
    return {
        "db_messages": total,
        "prompt_window": len(history),
        "window_limit": WINDOW,
        "db_keep_limit": DB_KEEP,
        "summary_chars": len(summary or ""),
        "has_summary": bool(summary),
        "retention_days": RETENTION_DAYS,
    }


def _cap_history_chars(history: list[dict]) -> list[dict]:
    total = 0
    kept = []
    for item in reversed(history):
        chunk = len(item.get("content") or "")
        if kept and total + chunk > MAX_HISTORY_CHARS:
            break
        kept.append(item)
        total += chunk
    kept.reverse()
    return kept


def _trim_overflow(chat_id, thread_id):
    """Hard-trim DB so memory cannot grow forever within retention window."""
    qs = TelegramChatMessage.objects.filter(
        chat_id=str(chat_id),
        thread_id=_thread_key(thread_id),
    ).order_by("-created")
    keep_ids = list(qs.values_list("pk", flat=True)[:DB_KEEP])
    if not keep_ids:
        return
    TelegramChatMessage.objects.filter(
        chat_id=str(chat_id),
        thread_id=_thread_key(thread_id),
    ).exclude(pk__in=keep_ids).delete()


def _cleanup_old(chat_id, thread_id):
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    TelegramChatMessage.objects.filter(
        chat_id=str(chat_id),
        thread_id=_thread_key(thread_id),
        created__lt=cutoff,
    ).delete()
