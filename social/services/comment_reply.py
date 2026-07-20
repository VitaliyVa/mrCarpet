"""HITL-відповіді на коменти соцмереж через сімейний чат.

Флоу:
1. Оператор reply-ить на алерт-копію комента в staff topic сирим текстом
   («нє, нема») → LLM робить ввічливу чернетку → бот шле її з кнопками
   [✅ Надіслати] [🔁 Інший варіант] [❌ Скасувати].
2. Reply на ЧЕРНЕТКУ новим текстом = інструкція для регенерації.
3. ✅ → відповідь летить у соцмережу: FB/IG — від імені сторінки (Graph),
   TG — від бота reply-ем у discussion-групі.

callback_data: crok:{id} / crre:{id} / crno:{id} (перехоплюється у webhook
ДО AI-агента, щоб його handle_callback не з'їв кнопки).
"""

from __future__ import annotations

import logging

import requests

from project.telegram_api import (
    answer_callback_query,
    edit_message_text,
    send_message,
)
from social.models import SocialCommentReply
from social.services.comment_notify import (
    PLATFORM_FACEBOOK,
    PLATFORM_INSTAGRAM,
    PLATFORM_LABELS,
    PLATFORM_TELEGRAM,
    _bot_token,
)
from social.services.reply_llm import ReplyLlmError, generate_reply

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TIMEOUT = 20

CB_SEND = "crok:"
CB_RETRY = "crre:"
CB_CANCEL = "crno:"


def _draft_keyboard(reply_id) -> dict:
    rid = str(reply_id)
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Надіслати", "callback_data": f"{CB_SEND}{rid}"},
                {"text": "🔁 Інший варіант", "callback_data": f"{CB_RETRY}{rid}"},
                {"text": "❌ Скасувати", "callback_data": f"{CB_CANCEL}{rid}"},
            ]
        ]
    }


def _draft_message_text(record: SocialCommentReply) -> str:
    platform = PLATFORM_LABELS.get(record.platform, record.platform)
    return (
        f"📝 Чернетка відповіді · {platform}\n"
        f"На комент: «{(record.comment_text or '')[:200]}»\n\n"
        f"{record.draft_text}\n\n"
        "✅ надіслати · 🔁 інший варіант · ❌ скасувати\n"
        "Або відповісти на це повідомлення уточненням — перегенерую."
    )


def maybe_handle_staff_reply(msg: dict) -> bool:
    """Reply оператора в staff topic → чернетка. True якщо це наш флоу."""
    if not msg:
        return False
    reply_to = msg.get("reply_to_message_id") or (
        (msg.get("reply_to_message") or {}).get("message_id")
    )
    if not reply_to:
        return False
    text = (msg.get("text") or "").strip()
    if not text or text.startswith("/"):
        return False

    chat_id = str((msg.get("chat") or {}).get("id") or "")
    record = (
        SocialCommentReply.objects.filter(
            alert_chat_id=chat_id, alert_message_id=str(reply_to)
        )
        .exclude(status__in=(SocialCommentReply.Status.SENT,))
        .order_by("-created")
        .first()
    )
    instruction = ""
    if record is None:
        # Може, це reply на чернетку → регенерація з інструкцією
        record = (
            SocialCommentReply.objects.filter(
                alert_chat_id=chat_id, draft_message_id=str(reply_to)
            )
            .exclude(status=SocialCommentReply.Status.SENT)
            .order_by("-created")
            .first()
        )
        if record is None:
            return False
        instruction = text
    else:
        record.raw_operator_text = text

    # Дедуп ретраїв Telegram: цей reply вже обробляли
    operator_mid = str(msg.get("message_id") or "")
    if operator_mid and record.last_operator_message_id == operator_mid:
        return True
    record.last_operator_message_id = operator_mid

    record.drafted_by_tg_user = str((msg.get("from") or {}).get("id") or "")
    thread_id = msg.get("message_thread_id")

    try:
        record.draft_text = generate_reply(
            platform=record.platform,
            comment_text=record.comment_text,
            operator_text=record.raw_operator_text,
            extra_instruction=instruction,
        )
    except ReplyLlmError as exc:
        logger.error("reply llm failed: %s", exc)
        send_message(
            f"⚠️ Не вдалося згенерувати відповідь ({exc}). "
            "Спробуй ще раз reply-ем на алерт.",
            chat_id=chat_id,
            message_thread_id=thread_id,
            reply_to_message_id=msg.get("message_id"),
        )
        return True

    record.status = SocialCommentReply.Status.AWAITING
    record.save()

    data = send_message(
        _draft_message_text(record),
        chat_id=chat_id,
        message_thread_id=thread_id,
        reply_to_message_id=msg.get("message_id"),
        reply_markup=_draft_keyboard(record.pk),
    )
    if data.get("ok"):
        mid = (data.get("result") or {}).get("message_id")
        if mid:
            record.draft_message_id = str(mid)
            record.save(update_fields=["draft_message_id", "updated"])
    return True


def handle_reply_callback(callback: dict) -> bool:
    """Кнопки чернетки. True якщо callback наш (префікс cr)."""
    data = callback.get("data") or ""
    if not data.startswith(("crok:", "crre:", "crno:")):
        return False
    cq_id = callback.get("id")
    message = callback.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    message_id = message.get("message_id")

    action, _, rid = data.partition(":")
    record = SocialCommentReply.objects.filter(pk=rid or 0).first()
    if record is None:
        answer_callback_query(cq_id, "Запис не знайдено", show_alert=True)
        return True
    if chat_id != str(record.alert_chat_id):
        answer_callback_query(cq_id, "Чужий чат", show_alert=True)
        return True
    if record.status == SocialCommentReply.Status.SENT:
        answer_callback_query(cq_id, "Вже надіслано")
        return True

    if action == "crno":
        record.status = SocialCommentReply.Status.CANCELLED
        record.save(update_fields=["status", "updated"])
        answer_callback_query(cq_id, "Скасовано")
        if message_id:
            edit_message_text(
                chat_id,
                message_id,
                f"❌ Скасовано\n\nНа комент: «{(record.comment_text or '')[:200]}»",
                reply_markup={"inline_keyboard": []},
            )
        return True

    if action == "crre":
        try:
            record.draft_text = generate_reply(
                platform=record.platform,
                comment_text=record.comment_text,
                operator_text=record.raw_operator_text,
                variation=True,
            )
            record.save(update_fields=["draft_text", "updated"])
            answer_callback_query(cq_id, "Новий варіант")
            if message_id:
                edit_message_text(
                    chat_id,
                    message_id,
                    _draft_message_text(record),
                    reply_markup=_draft_keyboard(record.pk),
                )
        except ReplyLlmError as exc:
            answer_callback_query(cq_id, f"LLM помилка: {exc}"[:190], show_alert=True)
        return True

    # crok — надіслати в соцмережу.
    # Атомарний claim: подвійний ✅ (два оператори/даблклік) не має
    # відправити клієнту дві відповіді.
    claimed = SocialCommentReply.objects.filter(
        pk=record.pk,
        status__in=(
            SocialCommentReply.Status.AWAITING,
            SocialCommentReply.Status.FAILED,
        ),
    ).update(status=SocialCommentReply.Status.SENDING)
    if not claimed:
        answer_callback_query(cq_id, "Вже обробляється")
        return True
    record.refresh_from_db()

    result = _send_platform_reply(record)
    if result.get("ok"):
        record.status = SocialCommentReply.Status.SENT
        record.sent_external_id = str(result.get("external_id") or "")
        record.save(update_fields=["status", "sent_external_id", "updated"])
        answer_callback_query(cq_id, "Надіслано ✅")
        if message_id:
            edit_message_text(
                chat_id,
                message_id,
                f"✅ Надіслано · {PLATFORM_LABELS.get(record.platform, record.platform)}\n\n"
                f"{record.draft_text}",
                reply_markup={"inline_keyboard": []},
            )
    else:
        record.status = SocialCommentReply.Status.FAILED
        record.error = str(result.get("error") or "")[:1000]
        record.save(update_fields=["status", "error", "updated"])
        answer_callback_query(cq_id, "Помилка відправки", show_alert=True)
        if message_id:
            edit_message_text(
                chat_id,
                message_id,
                f"💥 Не надіслано: {record.error[:300]}\n\n{record.draft_text}",
                reply_markup=_draft_keyboard(record.pk),
            )
    return True


def _send_platform_reply(record: SocialCommentReply) -> dict:
    text = (record.draft_text or "").strip()
    if not text:
        return {"ok": False, "error": "empty draft"}
    try:
        if record.platform == PLATFORM_FACEBOOK:
            return _fb_reply(record.external_comment_id, text)
        if record.platform == PLATFORM_INSTAGRAM:
            return _ig_reply(record.external_comment_id, text)
        if record.platform == PLATFORM_TELEGRAM:
            return _tg_reply(record.tg_chat_id, record.tg_message_id, text)
        return {"ok": False, "error": f"unknown platform {record.platform}"}
    except Exception as exc:
        logger.exception("platform reply failed")
        return {"ok": False, "error": str(exc)}


def _fb_reply(comment_id: str, text: str) -> dict:
    """Відповідь від імені сторінки: POST /{comment_id}/comments."""
    if not comment_id:
        return {"ok": False, "error": "no FB comment id"}
    from social.services.meta import MetaPublishError, _graph

    try:
        data = _graph("POST", f"{comment_id}/comments", data={"message": text})
        return {"ok": True, "external_id": data.get("id", "")}
    except MetaPublishError as exc:
        return {"ok": False, "error": str(exc)}


def _ig_reply(comment_id: str, text: str) -> dict:
    """Відповідь від імені IG-акаунта: POST /{comment_id}/replies."""
    if not comment_id:
        return {"ok": False, "error": "no IG comment id"}
    from social.services.meta import MetaPublishError, _graph

    try:
        data = _graph("POST", f"{comment_id}/replies", data={"message": text})
        return {"ok": True, "external_id": data.get("id", "")}
    except MetaPublishError as exc:
        return {"ok": False, "error": str(exc)}


def _tg_reply(chat_id: str, message_id: str, text: str) -> dict:
    """Reply у discussion-групі. Обмеження Bot API: від імені бота, не каналу."""
    if not chat_id or not message_id:
        return {"ok": False, "error": "no TG chat/message id"}
    token = _bot_token()
    if not token:
        return {"ok": False, "error": "bot token empty"}
    resp = requests.post(
        f"{TELEGRAM_API}/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": int(message_id),
        },
        timeout=TIMEOUT,
    )
    data = resp.json() if resp.content else {}
    if not data.get("ok"):
        return {"ok": False, "error": str(data)[:400]}
    return {
        "ok": True,
        "external_id": str((data.get("result") or {}).get("message_id") or ""),
    }
