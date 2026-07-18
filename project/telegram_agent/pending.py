"""Human-in-the-loop write actions."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from project.models import TelegramPendingAction
from project.telegram_api import (
    answer_callback_query,
    confirm_reject_keyboard,
    edit_message_text,
    send_message,
)

from .tools import describe_write, execute_write_tool, validate_write_args

TTL_MINUTES = 15


def create_pending_and_ask(
    *,
    tool_name: str,
    args: dict,
    chat_id,
    thread_id,
    tg_user_id,
    reply_to_message_id=None,
) -> tuple[bool, str]:
    ok, err, clean = validate_write_args(tool_name, args)
    if not ok:
        return False, err

    action = TelegramPendingAction.objects.create(
        tool_name=tool_name,
        args_json=clean,
        description=describe_write(tool_name, clean),
        created_by_tg_user=tg_user_id,
        chat_id=str(chat_id),
        message_thread_id="" if thread_id in (None, "") else str(thread_id),
        expires_at=timezone.now() + timedelta(minutes=TTL_MINUTES),
    )
    text = (
        "⚠️ Потрібне підтвердження\n\n"
        f"{action.description}\n\n"
        f"Діє {TTL_MINUTES} хв. Будь-хто з цієї групи може підтвердити."
    )
    data = send_message(
        text,
        chat_id=chat_id,
        message_thread_id=thread_id,
        reply_markup=confirm_reject_keyboard(str(action.id)),
        reply_to_message_id=reply_to_message_id,
    )
    if data.get("ok"):
        mid = (data.get("result") or {}).get("message_id")
        if mid:
            action.telegram_message_id = mid
            action.save(update_fields=["telegram_message_id"])
        return True, "Запит на підтвердження надіслано в чат."
    return False, "Не вдалося надіслати запит на підтвердження."


def handle_callback(callback: dict, settings) -> None:
    data = callback.get("data") or ""
    cq_id = callback.get("id")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")

    if str(settings.chat_id).strip() != chat_id:
        answer_callback_query(cq_id, "Чужий чат", show_alert=True)
        return

    if data.startswith("tgok:"):
        action_id = data[5:]
        _resolve(action_id, confirm=True, callback=callback)
    elif data.startswith("tgno:"):
        action_id = data[5:]
        _resolve(action_id, confirm=False, callback=callback)
    else:
        answer_callback_query(cq_id, "Невідома кнопка")


def _resolve(action_id: str, *, confirm: bool, callback: dict) -> None:
    cq_id = callback.get("id")
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")

    try:
        action = TelegramPendingAction.objects.get(pk=action_id)
    except (TelegramPendingAction.DoesNotExist, ValueError):
        answer_callback_query(cq_id, "Дію не знайдено", show_alert=True)
        return

    if str(action.chat_id) != str(chat_id):
        answer_callback_query(cq_id, "Чужий чат", show_alert=True)
        return

    if action.status != TelegramPendingAction.STATUS_PENDING:
        answer_callback_query(cq_id, f"Вже оброблено: {action.status}")
        return

    if action.expires_at and action.expires_at < timezone.now():
        action.status = TelegramPendingAction.STATUS_EXPIRED
        action.save(update_fields=["status", "updated"])
        answer_callback_query(cq_id, "Протерміновано", show_alert=True)
        if message_id:
            edit_message_text(
                chat_id,
                message_id,
                f"⏰ Протерміновано\n\n{action.description}",
                reply_markup={"inline_keyboard": []},
            )
        return

    if not confirm:
        action.status = TelegramPendingAction.STATUS_REJECTED
        action.result_text = "Скасовано користувачем"
        action.save(update_fields=["status", "result_text", "updated"])
        answer_callback_query(cq_id, "Скасовано")
        if message_id:
            edit_message_text(
                chat_id,
                message_id,
                f"❌ Скасовано\n\n{action.description}",
                reply_markup={"inline_keyboard": []},
            )
        return

    try:
        result = execute_write_tool(action.tool_name, action.args_json)
    except Exception as exc:
        action.status = TelegramPendingAction.STATUS_FAILED
        action.result_text = str(exc)[:1000]
        action.save(update_fields=["status", "result_text", "updated"])
        answer_callback_query(cq_id, "Помилка виконання", show_alert=True)
        if message_id:
            edit_message_text(
                chat_id,
                message_id,
                f"💥 Помилка\n\n{action.description}\n\n{exc}",
                reply_markup={"inline_keyboard": []},
            )
        return

    action.status = TelegramPendingAction.STATUS_CONFIRMED
    action.result_text = str(result)[:2000]
    action.save(update_fields=["status", "result_text", "updated"])
    answer_callback_query(cq_id, "Виконано")
    if message_id:
        edit_message_text(
            chat_id,
            message_id,
            f"✅ Виконано\n\n{action.description}\n\nРезультат: {result}",
            reply_markup={"inline_keyboard": []},
        )
