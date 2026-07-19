"""Низкорівневі виклики Telegram Bot API (requests)."""
import json
import logging
from typing import Sequence

import requests

from .models import TelegramSettings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_TIMEOUT_SECONDS = 30
TELEGRAM_UPLOAD_TIMEOUT_SECONDS = 60


def get_bot_token():
    settings = TelegramSettings.load()
    return (settings.bot_token or "").strip()


def api_call(method, payload=None, *, token=None, http="post"):
    token = token or get_bot_token()
    if not token:
        raise ValueError("Telegram bot_token empty")
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    if http == "get":
        response = requests.get(url, params=payload or {}, timeout=TELEGRAM_TIMEOUT_SECONDS)
    else:
        response = requests.post(url, json=payload or {}, timeout=TELEGRAM_TIMEOUT_SECONDS)
    data = response.json() if response.content else {}
    if not (response.ok and data.get("ok")):
        logger.warning("Telegram %s failed: %s %s", method, response.status_code, data)
    return data


def get_me(token=None):
    return api_call("getMe", http="get", token=token)


def send_message(
    text,
    *,
    chat_id=None,
    message_thread_id=None,
    reply_markup=None,
    reply_to_message_id=None,
    token=None,
    parse_mode=None,
):
    settings = TelegramSettings.load()
    chat_id = str(chat_id if chat_id is not None else settings.chat_id).strip()
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    thread = message_thread_id
    if thread is None:
        thread = (settings.message_thread_id or "").strip() or None
    if thread not in (None, ""):
        try:
            payload["message_thread_id"] = int(thread)
        except (TypeError, ValueError):
            payload["message_thread_id"] = thread
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    data = api_call("sendMessage", payload, token=token)
    # reply target may be gone / fake in tests — retry without reply
    if (
        not data.get("ok")
        and reply_to_message_id
        and "replied" in str(data.get("description", "")).lower()
    ):
        payload.pop("reply_to_message_id", None)
        data = api_call("sendMessage", payload, token=token)
    return data


def send_chat_action(
    action="typing",
    *,
    chat_id=None,
    message_thread_id=None,
    token=None,
):
    """Telegram typing / upload indicator (clears when next message is sent)."""
    settings = TelegramSettings.load()
    chat_id = str(chat_id if chat_id is not None else settings.chat_id).strip()
    payload = {"chat_id": chat_id, "action": action}
    thread = message_thread_id
    if thread is None:
        thread = (settings.message_thread_id or "").strip() or None
    if thread not in (None, ""):
        try:
            payload["message_thread_id"] = int(thread)
        except (TypeError, ValueError):
            payload["message_thread_id"] = thread
    return api_call("sendChatAction", payload, token=token)


def edit_message_text(chat_id, message_id, text, *, reply_markup=None, token=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text[:4000],
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return api_call("editMessageText", payload, token=token)


def answer_callback_query(callback_query_id, text="", *, show_alert=False, token=None):
    return api_call(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_query_id,
            "text": (text or "")[:200],
            "show_alert": show_alert,
        },
        token=token,
    )


def set_webhook(url, secret_token="", *, token=None):
    payload = {
        "url": url,
        "allowed_updates": ["message", "callback_query", "my_chat_member"],
        "drop_pending_updates": False,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    return api_call("setWebhook", payload, token=token)


def delete_webhook(*, drop_pending=False, token=None):
    return api_call(
        "deleteWebhook",
        {"drop_pending_updates": drop_pending},
        token=token,
    )


def get_updates(offset=None, timeout=25, *, token=None):
    payload = {
        "timeout": timeout,
        "allowed_updates": '["message","callback_query"]',
    }
    if offset is not None:
        payload["offset"] = offset
    token = token or get_bot_token()
    if not token:
        raise ValueError("Telegram bot_token empty")
    url = f"{TELEGRAM_API}/bot{token}/getUpdates"
    # client timeout must exceed Telegram long-poll timeout
    response = requests.get(
        url, params=payload, timeout=max(TELEGRAM_TIMEOUT_SECONDS, timeout + 10)
    )
    data = response.json() if response.content else {}
    if not (response.ok and data.get("ok")):
        logger.warning("Telegram getUpdates failed: %s %s", response.status_code, data)
    return data


def confirm_reject_keyboard(action_id: str):
    # callback_data max 64 bytes
    confirm = f"tgok:{action_id}"[:64]
    reject = f"tgno:{action_id}"[:64]
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Підтвердити", "callback_data": confirm},
                {"text": "❌ Скасувати", "callback_data": reject},
            ]
        ]
    }


def _thread_payload(message_thread_id=None):
    settings = TelegramSettings.load()
    thread = message_thread_id
    if thread is None:
        thread = (settings.message_thread_id or "").strip() or None
    if thread in (None, ""):
        return {}
    try:
        return {"message_thread_id": int(thread)}
    except (TypeError, ValueError):
        return {"message_thread_id": thread}


def send_photo(
    photo_bytes: bytes,
    *,
    filename: str = "chart.png",
    caption: str = "",
    chat_id=None,
    message_thread_id=None,
    reply_to_message_id=None,
    token=None,
):
    """Upload a PNG/JPEG photo (multipart)."""
    token = token or get_bot_token()
    if not token:
        raise ValueError("Telegram bot_token empty")
    settings = TelegramSettings.load()
    chat_id = str(chat_id if chat_id is not None else settings.chat_id).strip()
    url = f"{TELEGRAM_API}/bot{token}/sendPhoto"
    data = {"chat_id": chat_id}
    data.update(_thread_payload(message_thread_id))
    if caption:
        data["caption"] = caption[:1024]
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id
    files = {"photo": (filename, photo_bytes, "image/png")}
    response = requests.post(
        url, data=data, files=files, timeout=TELEGRAM_UPLOAD_TIMEOUT_SECONDS
    )
    payload = response.json() if response.content else {}
    if not (response.ok and payload.get("ok")):
        logger.warning(
            "Telegram sendPhoto failed: %s %s", response.status_code, payload
        )
    return payload


def send_media_group(
    photos: Sequence[tuple[str, bytes]],
    *,
    caption: str = "",
    chat_id=None,
    message_thread_id=None,
    reply_to_message_id=None,
    token=None,
):
    """
    Send 2–10 photos as an album.
    photos: list of (filename, bytes). Caption attaches to the first item.
    """
    token = token or get_bot_token()
    if not token:
        raise ValueError("Telegram bot_token empty")
    items = list(photos)[:10]
    if not items:
        return {"ok": False, "description": "empty media"}
    if len(items) == 1:
        return send_photo(
            items[0][1],
            filename=items[0][0],
            caption=caption,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            reply_to_message_id=reply_to_message_id,
            token=token,
        )

    settings = TelegramSettings.load()
    chat_id = str(chat_id if chat_id is not None else settings.chat_id).strip()
    url = f"{TELEGRAM_API}/bot{token}/sendMediaGroup"

    media = []
    files = {}
    for idx, (filename, blob) in enumerate(items):
        key = f"file{idx}"
        item = {"type": "photo", "media": f"attach://{key}"}
        if idx == 0 and caption:
            item["caption"] = caption[:1024]
        media.append(item)
        files[key] = (filename or f"chart_{idx}.png", blob, "image/png")

    data = {
        "chat_id": chat_id,
        "media": json.dumps(media, ensure_ascii=False),
    }
    data.update(_thread_payload(message_thread_id))
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id

    response = requests.post(
        url, data=data, files=files, timeout=TELEGRAM_UPLOAD_TIMEOUT_SECONDS
    )
    payload = response.json() if response.content else {}
    if not (response.ok and payload.get("ok")):
        logger.warning(
            "Telegram sendMediaGroup failed: %s %s", response.status_code, payload
        )
        # Fallback: send individually
        last = None
        for i, (filename, blob) in enumerate(items):
            last = send_photo(
                blob,
                filename=filename,
                caption=caption if i == 0 else "",
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                reply_to_message_id=reply_to_message_id if i == 0 else None,
                token=token,
            )
        return last or payload
    return payload
