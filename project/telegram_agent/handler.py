"""Update dispatcher: wake → LLM → tools / pending / reply."""
from __future__ import annotations

import logging
import threading
from typing import Any

from django.db import close_old_connections, IntegrityError

from project.models import TelegramProcessedUpdate, TelegramSettings
from project.telegram_api import get_me, send_chat_action, send_message

from . import llm as agent_llm
from .intent import fake_tool_narration_plan, maybe_direct_plan
from .memory import (
    append_message,
    get_memory_context,
    maybe_update_summary,
    user_rate_exceeded,
)
from .pending import create_pending_writes, handle_callback
from .tools import READ_TOOLS, WRITE_TOOLS, execute_read_tool
from .triggers import chat_allowed, should_wake

logger = logging.getLogger(__name__)

_bot_identity_cache: dict[str, Any] = {"id": None, "username": "", "token": ""}


def _bot_identity(settings: TelegramSettings):
    token = (settings.bot_token or "").strip()
    if _bot_identity_cache.get("token") == token and _bot_identity_cache.get("id"):
        return _bot_identity_cache["id"], _bot_identity_cache["username"]
    data = get_me(token=token)
    if not data.get("ok"):
        return None, ""
    result = data.get("result") or {}
    _bot_identity_cache["token"] = token
    _bot_identity_cache["id"] = result.get("id")
    _bot_identity_cache["username"] = result.get("username") or ""
    return _bot_identity_cache["id"], _bot_identity_cache["username"]


def mark_processed(update_id) -> bool:
    if update_id is None:
        return True
    try:
        TelegramProcessedUpdate.objects.create(update_id=int(update_id))
        return True
    except IntegrityError:
        return False
    except Exception:
        logger.exception("dedupe failed")
        return True


def unmark_processed(update_id) -> None:
    """Allow retry after failed AI processing (same update_id)."""
    if update_id is None:
        return
    try:
        TelegramProcessedUpdate.objects.filter(update_id=int(update_id)).delete()
    except Exception:
        logger.exception("unmark_processed failed")


def handle_update(update: dict) -> None:
    """Sync entry (webhook thread / poll)."""
    try:
        settings = TelegramSettings.load()
    except Exception:
        logger.exception("settings load")
        return

    if not settings.ai_ready:
        return

    update_id = update.get("update_id")
    if not mark_processed(update_id):
        return

    ai_started = False
    try:
        if "callback_query" in update:
            try:
                handle_callback(update["callback_query"], settings)
            except Exception:
                logger.exception("callback failed")
                unmark_processed(update_id)
            return

        message = update.get("message")
        if not message:
            return

        if not chat_allowed(message, settings):
            return

        bot_id, bot_username = _bot_identity(settings)
        if not should_wake(
            message,
            wake_words=settings.get_wake_words(),
            bot_username=bot_username,
            bot_id=bot_id,
        ):
            return

        tg_user = (message.get("from") or {})
        tg_user_id = tg_user.get("id")
        if user_rate_exceeded(tg_user_id, settings.ai_rate_limit_per_user):
            send_message(
                "⏳ Забагато запитів. Зачекай кілька хвилин.",
                chat_id=message["chat"]["id"],
                message_thread_id=message.get("message_thread_id"),
                reply_to_message_id=message.get("message_id"),
            )
            return

        ai_started = True
        _process_user_message(settings, message)
    except agent_llm.AgentLlmError as exc:
        logger.warning("agent llm error: %s", exc)
        if ai_started:
            unmark_processed(update_id)
        try:
            msg = update.get("message") or {}
            send_message(
                "⏳ Модель зараз недоступна (Replicate). Спробуй через хвилину.",
                chat_id=msg.get("chat", {}).get("id"),
                message_thread_id=msg.get("message_thread_id"),
                reply_to_message_id=msg.get("message_id"),
            )
        except Exception:
            pass
    except Exception:
        logger.exception("agent process failed")
        if ai_started:
            unmark_processed(update_id)
        try:
            msg = update.get("message") or {}
            send_message(
                "😕 Не зрозумів або сталась помилка. Спробуй ще раз коротше.",
                chat_id=msg.get("chat", {}).get("id"),
                message_thread_id=msg.get("message_thread_id"),
                reply_to_message_id=msg.get("message_id"),
            )
        except Exception:
            pass


def handle_update_async(update: dict) -> None:
    def _run():
        close_old_connections()
        try:
            handle_update(update)
        finally:
            close_old_connections()

    threading.Thread(target=_run, daemon=True, name="telegram-agent").start()


def _reply_context_text(message: dict) -> str:
    """Text of the message the user replied to (order notify, bot reply, etc.)."""
    replied = message.get("reply_to_message") or {}
    if not replied:
        return ""
    parts = []
    for key in ("text", "caption"):
        val = (replied.get(key) or "").strip()
        if val:
            parts.append(val)
    return "\n".join(parts)[:2000]


def _ask_writes(
    *,
    calls: list[dict],
    chat_id,
    thread_id,
    tg_user_id,
    msg_id,
    preview: str = "",
) -> None:
    ok, info = create_pending_writes(
        calls=calls,
        chat_id=chat_id,
        thread_id=thread_id,
        tg_user_id=tg_user_id,
        reply_to_message_id=msg_id,
    )
    if not ok:
        send_message(
            f"Не можу запропонувати дію: {info}",
            chat_id=chat_id,
            message_thread_id=thread_id,
            reply_to_message_id=msg_id,
        )
        append_message(chat_id, thread_id, "assistant", info)
        return
    note = info
    if preview:
        note = f"{preview}\n\n{info}"
        send_message(
            preview,
            chat_id=chat_id,
            message_thread_id=thread_id,
            reply_to_message_id=msg_id,
        )
    append_message(chat_id, thread_id, "assistant", note)


def _brief_tool_preview(tool_results: list[dict]) -> str:
    lines = ["📋 Перед підтвердженням:"]
    for item in tool_results:
        result = item.get("result") or {}
        name = item.get("name") or ""
        if name == "get_order" and result.get("ok"):
            o = result.get("order") or {}
            lines.append(
                f"№{o.get('order_number')} — {o.get('status_label')} — "
                f"{o.get('customer')} — {o.get('total_price')} грн"
            )
        elif name == "find_orders" and result.get("ok"):
            lines.append(f"Знайдено замовлень: {result.get('found', 0)}")
            for o in (result.get("orders") or [])[:3]:
                lines.append(
                    f"• №{o.get('order_number')} {o.get('status_label')} "
                    f"{o.get('customer')}"
                )
        else:
            lines.append(f"{name}: {str(result)[:200]}")
    return "\n".join(lines)[:1500]


def _process_user_message(settings: TelegramSettings, message: dict) -> None:
    chat_id = message["chat"]["id"]
    thread_id = message.get("message_thread_id")
    text = (message.get("text") or message.get("caption") or "").strip()
    reply_context = _reply_context_text(message)
    tg_user_id = (message.get("from") or {}).get("id")
    msg_id = message.get("message_id")
    model = (settings.replicate_model or "meta/meta-llama-3-8b-instruct").strip()

    try:
        send_chat_action("typing", chat_id=chat_id, message_thread_id=thread_id)
    except Exception:
        pass

    append_message(
        chat_id,
        thread_id,
        "user",
        text,
        tg_user_id=tg_user_id,
    )
    summary, history = get_memory_context(chat_id, thread_id)

    history_blob = "\n".join(
        (h.get("content") or "") for h in (history or [])[-8:]
    )
    context_for_intent = "\n".join(
        p for p in (reply_context, summary or "", history_blob) if p
    )

    tool_results: list[dict] = []
    plan = maybe_direct_plan(text, context_text=context_for_intent)
    if plan is None:
        plan = agent_llm.plan_once(
            model,
            summary=summary,
            history=history[:-1],
            user_text=text,
            reply_context=reply_context,
        )

    for _round in range(agent_llm.MAX_TOOL_ROUNDS + 1):
        ptype = (plan.get("type") or "").lower()

        if ptype == "reply":
            reply = (plan.get("text") or "").strip() or "Ок."
            if not tool_results:
                forced = fake_tool_narration_plan(reply) or maybe_direct_plan(
                    text, context_text=context_for_intent
                )
                if forced and forced.get("type") in ("tool", "tools", "write"):
                    plan = forced
                    continue
            send_message(
                reply,
                chat_id=chat_id,
                message_thread_id=thread_id,
                reply_to_message_id=msg_id,
            )
            append_message(chat_id, thread_id, "assistant", reply)
            maybe_update_summary(
                chat_id,
                thread_id,
                lambda old, recent: agent_llm.summarize(model, old, recent),
            )
            return

        if ptype == "write":
            name = plan.get("name") or ""
            args = plan.get("args") or {}
            if name not in WRITE_TOOLS:
                send_message(
                    f"Невідома write-дія: {name}",
                    chat_id=chat_id,
                    message_thread_id=thread_id,
                    reply_to_message_id=msg_id,
                )
                return
            _ask_writes(
                calls=[{"name": name, "args": args}],
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                msg_id=msg_id,
            )
            return

        calls = []
        if ptype == "tool":
            calls = [{"name": plan.get("name"), "args": plan.get("args") or {}}]
        elif ptype == "tools":
            calls = (plan.get("calls") or [])[: agent_llm.MAX_TOOLS_PER_TURN]
        else:
            reply = (plan.get("text") or str(plan))[:1500]
            send_message(
                reply,
                chat_id=chat_id,
                message_thread_id=thread_id,
                reply_to_message_id=msg_id,
            )
            append_message(chat_id, thread_id, "assistant", reply)
            return

        write_calls = []
        read_calls = []
        for call in calls:
            name = call.get("name") or ""
            if name in WRITE_TOOLS:
                write_calls.append(call)
            else:
                read_calls.append(call)

        # Reads first (preview), then one pending for all writes
        for call in read_calls:
            name = call.get("name") or ""
            args = call.get("args") or {}
            if name not in READ_TOOLS:
                tool_results.append({"name": name, "ok": False, "error": "not allowed"})
                continue
            result = execute_read_tool(name, args)
            tool_results.append({"name": name, "result": result})
            append_message(
                chat_id,
                thread_id,
                "tool",
                f"{name}: {result}",
            )

        if write_calls:
            preview = _brief_tool_preview(tool_results) if tool_results else ""
            _ask_writes(
                calls=write_calls,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                msg_id=msg_id,
                preview=preview,
            )
            return

        try:
            send_chat_action("typing", chat_id=chat_id, message_thread_id=thread_id)
        except Exception:
            pass

        plan = agent_llm.plan_once(
            model,
            summary=summary,
            history=history,
            user_text=text,
            tool_results=tool_results,
            reply_context=reply_context,
        )

    send_message(
        "Забагато кроків tool — спробуй конкретніше питання.",
        chat_id=chat_id,
        message_thread_id=thread_id,
        reply_to_message_id=msg_id,
    )
