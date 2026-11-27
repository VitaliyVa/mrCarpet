"""
Push order status changes made in OUR admin to Rozetka (PUT /orders/{id}).

Rozetka penalizes sellers who leave orders in «Нове» or do not hand over a
TTN, so when a manager moves a Rozetka order on in the admin, the matching
Rozetka status goes out by itself:

    our status                      Rozetka status (docs: OrdersStatuses)
    ------------------------------  ---------------------------------------
    paid «Оплачено, комплектується» 2  «Комплектується. Дані підтверджені»
    shipped + TTN                   3  «Передано в службу доставки» + ttn
                                       (ttn is required for 3; on refusal we
                                       retry with 2 + ttn, which Rozetka turns
                                       into 61 «Заплановано передачу
                                       перевізникові» by itself)
    cancelled + reason              the chosen cancel reason (42, 18, 40...)
    completed                       nothing: after a TTN Rozetka tracks the
                                       parcel and sets the final status itself
    admin action «Підтвердити»      26 «Опрацьовується менеджером»

Only admin saves call `push_for_change` (OrderAdmin.save_model). The poller's
own cancellation (rozetka_orders.cancel_order: Rozetka already cancelled it)
saves the order outside the admin, so it never echoes back to Rozetka. Site
orders (source="site") are never sent.

The call runs in a background thread started after the DB commit, so an admin
save never waits for Rozetka or fails because of it. The result is appended to
Order.message as one line:

    Rozetka ✓ [2] Комплектується. Дані підтверджені, 27.11 14:05
    Rozetka ✗ [3 ТТН 2045...] Передано в службу доставки, 27.11 14:05: <error>

The «✓ [key]» line is also the dedupe record: a push whose key already
succeeded for this order is not sent again (double click on the action, the
same status saved twice), so the same transition never reaches Rozetka twice.
Errors also go to Telegram, because a status Rozetka did not get costs rating.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field

from django.db import close_old_connections, transaction
from django.utils import timezone

from .rozetka_api import RozetkaClient, RozetkaError

logger = logging.getLogger(__name__)

MESSAGE_MAX = 1024

# Rozetka order statuses (docs: «Статуси замовлення [OrdersStatuses]»).
RZ_CONFIRMED = 2  # Комплектується. Дані підтверджені
RZ_SHIPPED = 3  # Передано в службу доставки (ttn required)
RZ_IN_PROGRESS = 26  # Опрацьовується менеджером

RZ_STATUS_NAMES = {
    RZ_CONFIRMED: "Комплектується. Дані підтверджені",
    RZ_SHIPPED: "Передано в службу доставки",
    RZ_IN_PROGRESS: "Опрацьовується менеджером",
    61: "Заплановано передачу перевізникові",
}

# Cancel reasons a seller sets from the cabinet (ids and names from the docs:
# OrdersStatuses and the search_status list of /v1/orders/search-data).
# Which of them Rozetka accepts from the current status is decided by
# status_available; a refusal is recorded with the ids it does allow.
CANCEL_REASONS = (
    (42, "Немає в наявності"),
    (43, "Брак"),
    (18, "Не вдалося зв'язатися з покупцем"),
    (28, "Некоректні контактні дані"),
    (40, "Клієнт передумав"),
    (17, "Не влаштовують умови оплати"),
    (24, "Не влаштовує доставка"),
    (29, "Ціна змінилася"),
)
RZ_STATUS_NAMES.update(CANCEL_REASONS)
CANCEL_SKIP = "skip"  # cancelled here only (e.g. already cancelled in the cabinet)


@dataclass(frozen=True)
class Push:
    status: int
    ttn: str = ""
    comment: str = ""
    # Send only if our order is still in this status when the thread runs, so
    # a quick «paid -> cancelled» does not send a stale «paid» after the cancel.
    our_status: str | None = None
    # Keys whose earlier success makes this push pointless.
    done_if: tuple = field(default=())

    @property
    def key(self) -> str:
        return f"{self.status} ТТН {self.ttn}" if self.ttn else str(self.status)

    @property
    def label(self) -> str:
        return RZ_STATUS_NAMES.get(self.status, f"статус {self.status}")


def is_rozetka(order) -> bool:
    from order.models import Order

    return bool(order.source == Order.SOURCE_ROZETKA and order.rozetka_order_id)


def push_for_change(order, before: dict | None, cancel_reason: str = "") -> Push | None:
    """The Rozetka push an admin save calls for, or None.

    `before` is {"status", "ttn"} from the DB before the save (None = new).
    """
    from order.models import Order

    if not is_rozetka(order) or before is None:
        return None
    old_status = before.get("status")
    old_ttn = (before.get("ttn") or "").strip()
    status = order.status
    ttn = (order.ttn or "").strip()

    if status == Order.STATUS_PAID and old_status != Order.STATUS_PAID:
        return Push(RZ_CONFIRMED, our_status=status)
    if status == Order.STATUS_SHIPPED and ttn and (
        old_status != Order.STATUS_SHIPPED or ttn != old_ttn
    ):
        return Push(RZ_SHIPPED, ttn=ttn, our_status=status)
    if status == Order.STATUS_CANCELLED and old_status != Order.STATUS_CANCELLED:
        reason = str(cancel_reason or "").strip()
        if not reason or reason == CANCEL_SKIP:
            return None
        try:
            reason_id = int(reason)
        except ValueError:
            return None
        if reason_id not in dict(CANCEL_REASONS):
            return None
        return Push(reason_id, comment=f"Скасовано продавцем: {dict(CANCEL_REASONS)[reason_id]}",
                    our_status=status)
    return None


def confirm_push() -> Push:
    """Admin action «Підтвердити на Rozetka»: order taken into work."""
    return Push(RZ_IN_PROGRESS, done_if=(str(RZ_IN_PROGRESS), str(RZ_CONFIRMED)))


# --- notes in Order.message ------------------------------------------------

NOTE_RE = re.compile(r"^Rozetka [✓✗] \[")


def _succeeded(message: str, key: str) -> bool:
    prefix = f"Rozetka ✓ [{key}]"
    return any(line.startswith(prefix) for line in (message or "").splitlines())


def already_done(message: str, push: Push) -> bool:
    if _succeeded(message, push.key):
        return True
    if any(_succeeded(message, k) for k in push.done_if):
        return True
    # Shipped with a TTN: nothing earlier makes sense to re-confirm.
    if push.status == RZ_IN_PROGRESS and any(
        line.startswith(f"Rozetka ✓ [{RZ_SHIPPED} ") for line in (message or "").splitlines()
    ):
        return True
    return False


def join_note(message: str | None, line: str) -> str:
    """Append `line`, dropping our oldest status notes first when too long.

    Import notes (Rozetka №, oversold lines that cancel_order reads) are kept.
    """
    line = line[:MESSAGE_MAX]
    lines = (message or "").splitlines()
    while len("\n".join(lines + [line])) > MESSAGE_MAX:
        index = next((i for i, text in enumerate(lines) if NOTE_RE.match(text)), None)
        if index is None:
            break
        del lines[index]
    old = "\n".join(lines)
    room = MESSAGE_MAX - len(line) - 1
    if len(old) > room:
        old = old[: max(room, 0)]
    return f"{old}\n{line}" if old else line


def _append_note(order_pk: int, line: str) -> None:
    from order.models import Order

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_pk).first()
        if order is None:
            return
        # update(), not save(): no signals, no `updated` bump that would look
        # like a manager edit.
        Order.objects.filter(pk=order_pk).update(message=join_note(order.message, line))


def _stamp() -> str:
    return timezone.localtime().strftime("%d.%m %H:%M")


def _allowed_now(client, rozetka_id: int) -> str:
    """«26, 2, 42» — statuses Rozetka accepts from the current one (best effort)."""
    try:
        data = client.get_order(rozetka_id, expand="status_available") or {}
        ids = []
        for item in data.get("status_available") or []:
            if isinstance(item, dict):
                value = item.get("child_id") or item.get("id")
            else:
                value = item
            if value not in (None, "") and str(value) not in ids:
                ids.append(str(value))
        return ", ".join(ids)
    except Exception:
        logger.info("rozetka: could not read status_available for %s", rozetka_id, exc_info=True)
        return ""


def _notify_error(order, push: Push, error: str) -> None:
    try:
        from project import telegram_utils

        if not telegram_utils._should_notify("order"):
            return
        number = order.order_number or order.rozetka_order_id
        text = (
            f"ROZETKA ⚠️ №{number}: статус «{push.label}» не передано на Rozetka.\n"
            f"{error[:300]}\n"
            "Змініть статус у кабінеті Rozetka вручну.\n"
            f"{telegram_utils.order_admin_absolute_url(order)}"
        )
        telegram_utils.send_telegram_message_async(text)
    except Exception:
        logger.exception("rozetka: telegram status-error notify failed for %s", order.pk)


# --- the call --------------------------------------------------------------

# One push at a time in this process: a double click cannot race two threads
# past the «already done» check for the same order.
_LOCK = threading.Lock()


def push_status(order_pk: int, push: Push, client=None) -> tuple[bool, str]:
    """Send one status to Rozetka and record the result. Never raises.

    Returns (sent_or_already_done, note line or reason).
    """
    from order.models import Order

    from .models import RozetkaSettings

    with _LOCK:
        try:
            order = Order.objects.filter(pk=order_pk).first()
            if order is None or not is_rozetka(order):
                return False, "не замовлення Rozetka"
            if push.our_status and order.status != push.our_status:
                return False, "статус уже змінився"
            if already_done(order.message, push):
                return True, "уже передано раніше"

            settings = RozetkaSettings.load()
            if client is None and not settings.is_configured:
                error = "інтеграцію Rozetka вимкнено або не задано логін"
                _append_note(order_pk, f"Rozetka ✗ [{push.key}] {push.label}, {_stamp()}: {error}")
                return False, error
            client = client or RozetkaClient(settings)
            rozetka_id = int(order.rozetka_order_id)
            via = ""
            try:
                client.change_status(rozetka_id, push.status, ttn=push.ttn or None,
                                     seller_comment=push.comment or None)
            except RozetkaError as first:
                if push.status != RZ_SHIPPED or not push.ttn:
                    raise
                # Docs: ttn with status 2 moves the order to 61 by itself.
                logger.info("rozetka: status 3 refused for %s (%s), trying 2 + ttn", rozetka_id, first)
                try:
                    client.change_status(rozetka_id, RZ_CONFIRMED, ttn=push.ttn)
                except RozetkaError as second:
                    raise RozetkaError(f"{first}; 2 + ТТН: {second}") from second
                via = " (через «Комплектується» + ТТН)"
            line = f"Rozetka ✓ [{push.key}] {push.label}{via}, {_stamp()}"
            _append_note(order_pk, line)
            return True, line
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            logger.warning("rozetka: status push %s for order %s failed: %s", push.key, order_pk, error)
            try:
                order = Order.objects.filter(pk=order_pk).first()
                if order is not None:
                    allowed = _allowed_now(client, int(order.rozetka_order_id)) if client else ""
                    if allowed:
                        error = f"{error} (зараз Rozetka дозволяє: {allowed})"
                    _append_note(
                        order_pk,
                        f"Rozetka ✗ [{push.key}] {push.label}, {_stamp()}: {error}"[:400],
                    )
                    _notify_error(order, push, error)
            except Exception:
                logger.exception("rozetka: could not record push error for order %s", order_pk)
            return False, error


def push_many(order_pks: list[int], push: Push) -> None:
    for pk in order_pks:
        push_status(pk, push)


def _run(fn, *args) -> None:
    close_old_connections()
    try:
        fn(*args)
    except Exception:
        logger.exception("rozetka: background status push crashed")
    finally:
        close_old_connections()


def start_background(fn, *args) -> None:
    """Separate thread (tests replace this to run inline)."""
    threading.Thread(target=_run, args=(fn, *args), daemon=True, name="rozetka-status").start()


def schedule(order_pk: int, push: Push) -> None:
    """After the admin's transaction commits, push in the background."""
    transaction.on_commit(lambda: start_background(push_status, order_pk, push))


def schedule_many(order_pks: list[int], push: Push) -> None:
    pks = list(order_pks)
    if pks:
        transaction.on_commit(lambda: start_background(push_many, pks, push))
