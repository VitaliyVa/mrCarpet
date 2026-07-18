"""Низкорівневі виклики Telegram Bot API (requests)."""
import logging

import requests

from .models import TelegramSettings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_TIMEOUT_SECONDS = 30


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
):
    settings = TelegramSettings.load()
    chat_id = str(chat_id if chat_id is not None else settings.chat_id).strip()
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": True,
    }
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
