"""Human-in-the-loop write actions."""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from project.models import TelegramPendingAction
from project.telegram_api import (
    answer_callback_query,
    confirm_reject_keyboard,
    edit_message_text,
    send_message,
)

from .memory import append_message
from .tools import (
    BATCH_TOOL,
    WRITE_TOOLS,
    describe_write,
    execute_write_calls,
    execute_write_tool,
    format_write_result_ua,
    validate_write_args,
    validate_write_calls,
)

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
    return create_pending_writes(
        calls=[{"name": tool_name, "args": args}],
        chat_id=chat_id,
        thread_id=thread_id,
        tg_user_id=tg_user_id,
        reply_to_message_id=reply_to_message_id,
    )


def create_pending_writes(
    *,
    calls: list[dict],
    chat_id,
    thread_id,
    tg_user_id,
    reply_to_message_id=None,
) -> tuple[bool, str]:
    """
    Create one pending confirmation for 1..N write tools.
    Multiple writes (status + email) share one ✅/❌.
    """
    if not calls:
        return False, "немає дій"

    if len(calls) == 1:
        tool_name = (calls[0].get("name") or "").strip()
        args = calls[0].get("args") or {}
        if tool_name not in WRITE_TOOLS:
            return False, f"unknown write tool: {tool_name}"
        ok, err, clean = validate_write_args(tool_name, args)
        if not ok:
            return False, err
        stored_name = tool_name
        stored_args = clean
        description = describe_write(tool_name, clean)
    else:
        ok, err, steps = validate_write_calls(calls)
        if not ok:
            return False, err
        stored_name = BATCH_TOOL
        stored_args = {"steps": steps}
        description = describe_write(BATCH_TOOL, stored_args)

    action = TelegramPendingAction.objects.create(
        tool_name=stored_name,
        args_json=stored_args,
        description=description,
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


def _run_action(action: TelegramPendingAction) -> dict:
    if action.tool_name == BATCH_TOOL:
        steps = (action.args_json or {}).get("steps") or []
        return execute_write_calls(steps)
    result = execute_write_tool(action.tool_name, action.args_json)
    return result


def _resolve(action_id: str, *, confirm: bool, callback: dict) -> None:
    cq_id = callback.get("id")
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    thread_id = message.get("message_thread_id")

    with transaction.atomic():
        try:
            action = (
                TelegramPendingAction.objects.select_for_update()
                .get(pk=action_id)
            )
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

        # Claim before external side-effects (SMTP) so double-✅ can't re-enter
        action.status = TelegramPendingAction.STATUS_CONFIRMED
        action.save(update_fields=["status", "updated"])

    try:
        result = _run_action(action)
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

    summary = format_write_result_ua(action.tool_name, result)
    all_ok = bool(result.get("ok"))
    if not all_ok:
        action.status = TelegramPendingAction.STATUS_FAILED
        action.result_text = summary[:2000]
        action.save(update_fields=["status", "result_text", "updated"])
        answer_callback_query(cq_id, "Частково / помилка", show_alert=True)
        final_text = f"⚠️ Не повністю\n\n{action.description}\n\n{summary}"
    else:
        action.result_text = summary[:2000]
        action.save(update_fields=["result_text", "updated"])
        answer_callback_query(cq_id, "Виконано")
        final_text = f"✅ Виконано\n\n{action.description}\n\n{summary}"

    if message_id:
        edit_message_text(
            chat_id,
            message_id,
            final_text,
            reply_markup={"inline_keyboard": []},
        )
    try:
        append_message(
            chat_id,
            thread_id if thread_id is not None else action.message_thread_id,
            "assistant",
            summary,
        )
    except Exception:
        pass
