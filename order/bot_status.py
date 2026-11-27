"""«🔄 Статус» under an order in the shop Telegram chat.

Flow:
  ordst:<pk>            menu: the current status and where it can go
  ordgo:<pk>:<s>        what will happen automatically, plus «✅ Так» / «↩️ Назад»
                        (for «Відправлено» it asks for the TTN instead)
  ordok:<pk>:<s>[:<r>]  apply; <r> is the Rozetka cancel reason id or "skip"
  ordttn:<pk>           ask for a (new) TTN
A reply with the TTN to the bot's «ТТН для замовлення ... [#pk]» message sets
the TTN and «Відправлено» in one go.

The save goes through Order.save(), so every signal the admin triggers runs
here too (stock back on cancel, the shipped letter, GA4 purchase, completed_at),
and Rozetka orders get the same status push the admin sends.
"""

from __future__ import annotations

import html
import logging
import re

from django.db import transaction

logger = logging.getLogger(__name__)

CODES = {
    "n": "new",
    "w": "awaiting_payment",
    "p": "paid",
    "s": "shipped",
    "c": "completed",
    "x": "cancelled",
}
CODE_OF = {v: k for k, v in CODES.items()}
MENU_ORDER = ("s", "c", "x", "p", "w", "n")
TTN_PROMPT = "ТТН для замовлення"
TTN_PROMPT_RE = re.compile(r"\[#(\d+)\]")


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _label(status: str) -> str:
    from order.models import Order

    return dict(Order.STATUS_CHOICES).get(status, status)


def _number(order) -> str:
    return str(order.order_number or order.pk)


# --------------------------------------------------------------- texts ---


def menu(order) -> tuple[str, dict]:
    current = order.status
    text = (
        f"🔄 Замовлення №{_number(order)}\n"
        f"Зараз: «{_label(current)}»"
        + (f"\nТТН: {order.ttn}" if (order.ttn or "").strip() else "")
        + (f"\nНова Пошта: {order.np_status}" if order.np_status else "")
        + "\n\nНа який статус змінити?"
    )
    buttons = [
        {"text": _label(CODES[c]), "callback_data": f"ordgo:{order.pk}:{c}"}
        for c in MENU_ORDER
        if CODES[c] != current
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    if current == "shipped":
        rows.append([{"text": "✏️ Змінити ТТН", "callback_data": f"ordttn:{order.pk}"}])
    return text, {"inline_keyboard": rows}


def consequences(order, status: str) -> list[str]:
    """What saving `status` will do by itself, in plain words."""
    from order.models import Order
    from order.shipping import has_real_email
    from order.stock import returnable_units
    from project.rozetka_status import is_rozetka

    rozetka = is_rozetka(order)
    cash = order.payment_type == Order.PAYMENT_CASH
    lines: list[str] = []
    if status == Order.STATUS_CANCELLED:
        units = returnable_units(order)
        lines.append(
            f"• Килим повернеться на склад: {units} шт." if units
            else "• На склад нічого не повертається (вже повернуто або метраж)"
        )
        if order.promocode_id:
            lines.append("• Промокод звільниться")
        if rozetka:
            lines.append("• Розетка отримає скасування з причиною, яку оберете")
        lines.append("• Покупцю нічого не надсилається")
    elif status == Order.STATUS_SHIPPED:
        lines.append("• Треба ТТН (14 цифр)")
        if rozetka:
            lines.append("• ТТН піде на Розетку, далі вона сама повідомляє покупця")
        elif has_real_email(order):
            lines.append(f"• Покупцю піде лист з ТТН на {order.email}")
        else:
            lines.append("• Email немає: дам текст з ТТН для Viber")
        lines.append("• Нова Пошта сама надішле покупцю SMS")
        if not rozetka:
            lines.append("• Стежитиму за посилкою: напишу, коли прибуде, і якщо не забирають")
    elif status == Order.STATUS_COMPLETED:
        if cash and not order.ga4_mp_sent:
            lines.append("• У Google піде «покупка» (для реклами)")
        if not rozetka:
            lines.append(
                "• Через 10 днів покупцю піде прохання про відгук"
                if has_real_email(order)
                else "• Через 10 днів дам сюди текст з проханням про відгук"
            )
    elif status == Order.STATUS_PAID:
        if rozetka:
            lines.append("• Розетка отримає «Комплектується»")
        if cash and not order.ga4_mp_sent:
            lines.append("• У Google піде «покупка» (для реклами)")
    if order.status == Order.STATUS_CANCELLED and status != Order.STATUS_CANCELLED and order.stock_returned:
        lines.append("• Килим знову спишеться зі складу")
    if not lines:
        lines.append("• Нічого автоматично не відбудеться")
    return lines


def preview(order, status: str) -> tuple[str, dict]:
    from project.rozetka_status import CANCEL_REASONS, CANCEL_SKIP, is_rozetka

    text = (
        f"Замовлення №{_number(order)}: «{_label(order.status)}» → «{_label(status)}»\n"
        "Що станеться:\n" + "\n".join(consequences(order, status))
    )
    code = CODE_OF[status]
    back = {"text": "↩️ Назад", "callback_data": f"ordst:{order.pk}"}
    if status == "cancelled" and is_rozetka(order):
        rows = [
            [{"text": name, "callback_data": f"ordok:{order.pk}:x:{rid}"}]
            for rid, name in CANCEL_REASONS
        ]
        rows.append([{"text": "Тільки тут (на Розетці вже скасовано)",
                      "callback_data": f"ordok:{order.pk}:x:{CANCEL_SKIP}"}])
        rows.append([back])
        return text + "\n\nОберіть причину для Розетки:", {"inline_keyboard": rows}
    return text, {
        "inline_keyboard": [[
            {"text": "✅ Так, змінити", "callback_data": f"ordok:{order.pk}:{code}"},
            back,
        ]]
    }


def ttn_prompt(order) -> str:
    return (
        f"✍️ {TTN_PROMPT} №{_number(order)} [#{order.pk}]\n"
        "Надішліть номер накладної відповіддю на це повідомлення "
        "(свайп вліво або «Відповісти»). Після цього статус стане «Відправлено»."
    )


# --------------------------------------------------------------- apply ---


def apply_status(order_pk: int, status: str, *, ttn: str = "", cancel_reason: str = "") -> tuple[bool, str]:
    """Save the new status like the admin does. Returns (ok, message)."""
    from order.models import Order
    from project import rozetka_status

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_pk).first()
        if order is None:
            return False, "Замовлення не знайдено"
        before = {"status": order.status, "ttn": order.ttn}
        rozetka = rozetka_status.is_rozetka(order)
        if status == Order.STATUS_SHIPPED and not (ttn or (order.ttn or "").strip()):
            return False, "Потрібна ТТН"
        if status == Order.STATUS_CANCELLED and rozetka and not cancel_reason:
            return False, "Оберіть причину скасування для Розетки"
        if status == order.status and not (ttn and ttn != order.ttn):
            return False, f"Статус уже «{_label(status)}»"
        order.status = status
        if ttn:
            order.ttn = ttn
        order.save()
    push = None
    try:
        push = rozetka_status.push_for_change(order, before, cancel_reason)
        if push is not None:
            rozetka_status.schedule(order.pk, push)
    except Exception:
        logger.exception("bot: rozetka push failed for order %s", order.pk)
        return True, "Статус змінено, але на Розетку не передано. Змініть у кабінеті Розетки."
    order.refresh_from_db()
    done = [f"✅ №{_number(order)}: «{_label(before['status'])}» → «{_label(order.status)}»"]
    if order.status == Order.STATUS_CANCELLED and order.stock_returned and before["status"] != Order.STATUS_CANCELLED:
        done.append("Килим повернено на склад")
    if push is not None:
        done.append(f"Розетка: передаю «{push.label}», результат буде в полі «Повідомлення»")
    return True, "\n".join(done)


def _after_shipped(order, chat_id, thread_id, reply_to) -> None:
    """Email went out by the signal; without email hand over a messenger text."""
    from order.customer_contact import messenger_buttons
    from order.shipping import has_real_email, shipped_messenger_text
    from project.rozetka_status import is_rozetka
    from project.telegram_api import send_message

    if is_rozetka(order):
        return
    if has_real_email(order):
        send_message(
            f"✉️ Лист з ТТН іде на {_esc(order.email)}. Нова Пошта теж надішле SMS. "
            "Стежу за посилкою.",
            chat_id=chat_id, message_thread_id=thread_id, reply_to_message_id=reply_to,
            parse_mode="HTML",
        )
        return
    send_message(
        "Email немає. Нова Пошта сама надішле покупцю SMS з ТТН, тож це за бажанням.\n"
        "Текст для Viber (натисніть, щоб скопіювати):\n"
        f"<pre>{_esc(shipped_messenger_text(order))}</pre>\nСтежу за посилкою.",
        chat_id=chat_id, message_thread_id=thread_id, reply_to_message_id=reply_to,
        reply_markup=messenger_buttons(order), parse_mode="HTML",
    )


# ------------------------------------------------------------ telegram ---


def _is_notification(message: dict) -> bool:
    """Order cards (new order, tracking news) carry the messenger-text button."""
    rows = ((message.get("reply_markup") or {}).get("inline_keyboard")) or []
    return any(
        str(button.get("callback_data") or "").startswith("ordtx:")
        for row in rows
        for button in row
    )


def _allowed(chat_id: str) -> bool:
    from project.models import TelegramSettings

    return bool(chat_id) and chat_id == str(TelegramSettings.load().chat_id or "").strip()


def handle_status_callback(callback: dict) -> bool:
    data = callback.get("data") or ""
    parts = data.split(":")
    if parts[0] not in ("ordst", "ordgo", "ordok", "ordttn"):
        return False

    from order.models import Order
    from project.telegram_api import answer_callback_query, edit_message_text, send_message

    cq_id = callback.get("id")
    message = callback.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    thread_id = message.get("message_thread_id")
    message_id = message.get("message_id")
    try:
        if not _allowed(chat_id):
            answer_callback_query(cq_id, "Чужий чат", show_alert=True)
            return True
        order = Order.objects.filter(pk=int(parts[1] if len(parts) > 1 else 0)).first()
        if order is None:
            answer_callback_query(cq_id, "Замовлення не знайдено", show_alert=True)
            return True
        action = parts[0]
        if action == "ordst":
            text, markup = menu(order)
            if _is_notification(message):  # keep the order card, open a menu under it
                send_message(text, chat_id=chat_id, message_thread_id=thread_id,
                             reply_to_message_id=message_id, reply_markup=markup)
            else:  # our own menu / result message: update it in place
                edit_message_text(chat_id, message_id, text, reply_markup=markup)
        elif action == "ordttn":
            send_message(ttn_prompt(order), chat_id=chat_id, message_thread_id=thread_id,
                         reply_markup={"force_reply": True, "input_field_placeholder": "20450012345678"})
        elif action == "ordgo":
            status = CODES.get(parts[2] if len(parts) > 2 else "")
            if not status:
                answer_callback_query(cq_id, "Невідомий статус", show_alert=True)
                return True
            text, markup = preview(order, status)
            edit_message_text(chat_id, message_id, text, reply_markup=markup)
            if status == Order.STATUS_SHIPPED:
                send_message(ttn_prompt(order), chat_id=chat_id, message_thread_id=thread_id,
                             reply_markup={"force_reply": True, "input_field_placeholder": "20450012345678"})
        elif action == "ordok":
            status = CODES.get(parts[2] if len(parts) > 2 else "")
            reason = parts[3] if len(parts) > 3 else ""
            if not status:
                answer_callback_query(cq_id, "Невідомий статус", show_alert=True)
                return True
            if status == Order.STATUS_SHIPPED and not (order.ttn or "").strip():
                send_message(ttn_prompt(order), chat_id=chat_id, message_thread_id=thread_id,
                             reply_markup={"force_reply": True})
                answer_callback_query(cq_id, "Спершу ТТН")
                return True
            ok, result = apply_status(order.pk, status, cancel_reason=reason)
            edit_message_text(chat_id, message_id, result,
                              reply_markup={"inline_keyboard": [[{"text": "🔄 Статус", "callback_data": f"ordst:{order.pk}"}]]})
            if ok and status == Order.STATUS_SHIPPED:
                order.refresh_from_db()
                _after_shipped(order, chat_id, thread_id, message_id)
        answer_callback_query(cq_id)
    except Exception:
        logger.exception("status callback failed: %s", data)
        try:
            answer_callback_query(cq_id, "Помилка, спробуйте ще раз", show_alert=True)
        except Exception:
            pass
    return True


def handle_ttn_reply(message: dict) -> bool:
    """A reply to our TTN prompt. True when handled (so the AI agent skips it)."""
    reply_to = message.get("reply_to_message") or {}
    prompt = reply_to.get("text") or ""
    if TTN_PROMPT not in prompt:
        return False
    match = TTN_PROMPT_RE.search(prompt)
    if not match:
        return False

    from order.models import Order
    from order.shipping import normalize_ttn
    from project.telegram_api import send_message

    chat_id = str((message.get("chat") or {}).get("id") or "")
    thread_id = message.get("message_thread_id")
    message_id = message.get("message_id")
    if not _allowed(chat_id):
        return True
    try:
        order = Order.objects.filter(pk=int(match.group(1))).first()
        if order is None:
            send_message("Замовлення не знайдено", chat_id=chat_id, message_thread_id=thread_id,
                         reply_to_message_id=message_id)
            return True
        ttn = normalize_ttn(message.get("text"))
        if not ttn:
            send_message(
                "Це не схоже на ТТН Нової Пошти: потрібно 14 цифр. "
                "Надішліть ще раз відповіддю на повідомлення з проханням про ТТН.",
                chat_id=chat_id, message_thread_id=thread_id, reply_to_message_id=message_id,
            )
            return True
        ok, result = apply_status(order.pk, Order.STATUS_SHIPPED, ttn=ttn)
        send_message(result, chat_id=chat_id, message_thread_id=thread_id,
                     reply_to_message_id=message_id,
                     reply_markup={"inline_keyboard": [[{"text": "🔄 Статус", "callback_data": f"ordst:{order.pk}"}]]})
        if ok:
            order.refresh_from_db()
            _after_shipped(order, chat_id, thread_id, message_id)
    except Exception:
        logger.exception("ttn reply failed")
        send_message("Помилка, спробуйте ще раз", chat_id=chat_id, message_thread_id=thread_id,
                     reply_to_message_id=message_id)
    return True
