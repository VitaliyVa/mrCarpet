"""Wake / mention / reply detection."""
from __future__ import annotations

import re
import unicodedata


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.casefold()
    text = text.replace("ʼ", "'").replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compact(text: str) -> str:
    return re.sub(r"[\s.\-_]+", "", _normalize(text))


def message_mentions_bot(message: dict, bot_username: str) -> bool:
    if not bot_username:
        return False
    uname = bot_username.lstrip("@").casefold()
    text = message.get("text") or message.get("caption") or ""
    if f"@{uname}" in text.casefold():
        return True
    for ent in message.get("entities") or []:
        if ent.get("type") == "mention":
            frag = text[ent["offset"] : ent["offset"] + ent["length"]]
            if frag.lstrip("@").casefold() == uname:
                return True
        if ent.get("type") == "text_mention":
            user = ent.get("user") or {}
            if user.get("is_bot") and user.get("username", "").casefold() == uname:
                return True
    return False


def is_reply_to_bot(message: dict, bot_id: int | None) -> bool:
    reply = message.get("reply_to_message") or {}
    frm = reply.get("from") or {}
    if not frm.get("is_bot"):
        return False
    if bot_id is not None and frm.get("id") != bot_id:
        return False
    return True


def contains_wake_word(text: str, wake_words: list[str]) -> bool:
    norm = _normalize(text)
    compact = _compact(text)
    for raw in wake_words or []:
        w = _normalize(raw)
        if not w:
            continue
        if w in norm:
            return True
        if _compact(raw) and _compact(raw) in compact:
            return True
    return False


def should_wake(
    message: dict,
    *,
    wake_words: list[str],
    bot_username: str,
    bot_id: int | None,
) -> bool:
    frm = message.get("from") or {}
    if frm.get("is_bot"):
        return False
    text = message.get("text") or message.get("caption") or ""
    if not text.strip():
        return False
    if message_mentions_bot(message, bot_username):
        return True
    if is_reply_to_bot(message, bot_id):
        return True
    if contains_wake_word(text, wake_words):
        return True
    return False


def chat_allowed(message: dict, settings) -> bool:
    chat = message.get("chat") or {}
    expected = str(settings.chat_id or "").strip()
    if not expected:
        return False
    if str(chat.get("id")) != expected:
        return False
    configured_thread = (settings.message_thread_id or "").strip()
    if configured_thread:
        msg_thread = message.get("message_thread_id")
        if msg_thread is None:
            return False
        if str(msg_thread) != configured_thread:
            return False
    return True
