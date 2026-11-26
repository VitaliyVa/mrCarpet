"""
Buyer messages from Rozetka -> Telegram.

`notify_new_messages(client=None) -> {"sent": n, "errors": [...]}`. Never raises.

Called by the rozetka-poller on every pass (project/management/commands/
rozetka_poll.py). Sources, each fetched in its own try/except:

  * chats msgType=items  (GET /messages/search): type 1 product question,
    type 2 question to the seller ("Написати продавцю")
  * chats msgType=orders (GET /messages/search): type 0, chats inside an order
  * item comments (GET /item-comments/search?expand=children): questions and
    reviews under our goods, plus buyer replies in their threads
  * calls (GET /calls/search): customer requests passed on by Rozetka

Who wrote a chat message (apidoc, Messages group): sender 0 system message to
the seller, 1 system message to the buyer, 2 our manager, 3 the buyer. Only
sender 3 goes to Telegram (and never a message with seller_id set). Comment
replies carry is_market (1 = written by the shop) and seller_id.

Dedup: RozetkaNotice.key, one row per event, created only after Telegram
accepted the message, so a failed send is retried on the next pass. Nothing is
marked read on Rozetka. Only events from the last LOOKBACK_DAYS are taken and
at most MAX_TELEGRAM_PER_PASS messages go out per pass (oldest first), so the
first enable does not flood the chat; the rest follows on the next passes.
"""

from __future__ import annotations

import hashlib
import html
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from django.db import IntegrityError

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 2
MAX_TELEGRAM_PER_PASS = 20
TEXT_LIMIT = 1500          # one buyer text inside a Telegram message
CHAT_BLOCK_LIMIT = 3000    # several messages of one chat combined (Telegram max is 4096)
SELLER_CABINET_URL = "https://seller.rozetka.com.ua/"
HEADER = "ROZETKA 💬"

SENDER_BUYER = 3
try:  # Rozetka dates are Kyiv local time, without an offset
    ROZETKA_TZ = ZoneInfo("Europe/Kyiv")
except Exception:  # no tz database: a fixed offset is close enough for a 2-day window
    ROZETKA_TZ = timezone(timedelta(hours=2))

CHAT_KINDS = {
    0: "order",
    1: "item",
    2: "seller",
}

CALL_TYPES = {
    1: "Прохання зв'язатися",
    2: "Уточнення по доставці",
    3: "Скасування замовлення",
    4: "Скарга",
    5: "Повернення",
    6: "Виправлення інформації на сайті",
    7: "Питання по оплаті",
}


@dataclass
class Event:
    """One Telegram message to send and the notice keys it settles."""

    keys: list[str]
    kind: str
    text: str
    sort_key: str = ""
    extra: dict = field(default_factory=dict)


# --- small helpers ---------------------------------------------------------


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _attr(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _trim(text: str, limit: int = TEXT_LIMIT) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _is_truthy_id(value) -> bool:
    """seller_id / is_market may come as None, 0, "0", "" or a real id."""
    if value in (None, "", False):
        return False
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return bool(str(value).strip())


def _parse_dt(value):
    """Rozetka dates: "2017-08-14 22:15:25" (sometimes with .microseconds)."""
    text = _clean(value)
    if not text:
        return None
    text = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def rozetka_now() -> datetime:
    return datetime.now(ROZETKA_TZ).replace(tzinfo=None)


def _is_recent(value, since: datetime) -> bool:
    """Unknown or unparsable dates count as recent (better twice than never)."""
    parsed = _parse_dt(value)
    return parsed is None or parsed >= since


def _link(url) -> str:
    url = _clean(url)
    if url.startswith("https://") or url.startswith("http://"):
        return url
    return ""


def _item_info(item) -> tuple[str, str]:
    """(name, url) of a Rozetka ItemModel, both may be empty."""
    if not isinstance(item, dict):
        return "", ""
    name = _clean(item.get("name_ua")) or _clean(item.get("name")) or _clean(item.get("title"))
    return name, _link(item.get("url"))


def _product_line(name: str, url: str) -> str:
    if url:
        label = _esc(name) if name else "товар на Rozetka"
        return f'Товар: <a href="{_attr(url)}">{label}</a>'
    if name:
        return f"Товар: {_esc(name)}"
    return ""


def _footer() -> str:
    return f'<a href="{_attr(SELLER_CABINET_URL)}">Відповісти в кабінеті продавця</a>'


def _compose(kind_label: str, lines: list[str], body_lines: list[str]) -> str:
    parts = [f"<b>{HEADER} {_esc(kind_label)}</b>"]
    parts.extend(line for line in lines if line)
    if body_lines:
        parts.append("")
        parts.extend(body_lines)
    parts.append("")
    parts.append(_footer())
    return "\n".join(parts)


def message_key(message: dict) -> str:
    """Stable key of a chat message: its id, else created + short hash of body."""
    msg_id = message.get("id")
    if msg_id not in (None, ""):
        return str(msg_id)
    created = _clean(message.get("created")).replace(" ", "T")
    digest = hashlib.sha1(_clean(message.get("body")).encode("utf-8")).hexdigest()[:10]
    return f"{created}-{digest}"


def is_buyer_message(message: dict) -> bool:
    if _is_truthy_id(message.get("seller_id")) or message.get("seller"):
        return False
    sender = message.get("sender")
    if sender in (None, ""):
        return True  # no sender field and no seller: treat as buyer
    try:
        return int(sender) == SENDER_BUYER
    except (TypeError, ValueError):
        return False


# --- chats -----------------------------------------------------------------


def _chat_kind_label(chat: dict) -> str:
    try:
        chat_type = int(chat.get("type"))
    except (TypeError, ValueError):
        chat_type = None
    kind = CHAT_KINDS.get(chat_type)
    if kind == "order" or (kind is None and chat.get("order_id")):
        order_id = chat.get("order_id") or (chat.get("order_data") or {}).get("id")
        return f"Повідомлення по замовленню №{order_id}" if order_id else "Повідомлення по замовленню"
    if kind == "item":
        return "Питання про товар"
    if kind == "seller":
        return "Питання продавцю"
    return "Повідомлення"


def _chat_buyer(chat: dict) -> str:
    name = _clean(chat.get("user_fio"))
    if not name and isinstance(chat.get("user"), dict):
        name = _clean(chat["user"].get("contact_fio"))
    return name


def chat_events(chat: dict, since: datetime, client=None, is_sent=None) -> list[Event]:
    """New buyer messages of one chat; several are combined into one Event.
    is_sent(key) skips messages already in Telegram, so a combined message
    never repeats an old one."""
    chat_id = chat.get("id")
    if chat_id in (None, ""):
        return []
    messages = chat.get("messages")
    if messages is None and client is not None:
        messages = (client.get_chat(int(chat_id)) or {}).get("messages")
    new = []
    for message in messages or []:
        if not isinstance(message, dict) or not is_buyer_message(message):
            continue
        if not _clean(message.get("body")) and not message.get("files"):
            continue
        if not _is_recent(message.get("created"), since):
            continue
        if is_sent and is_sent(f"chat:{chat_id}:{message_key(message)}"):
            continue
        new.append(message)
    if not new:
        return []
    new.sort(key=lambda m: _clean(m.get("created")))

    kind_label = _chat_kind_label(chat)
    name, url = _item_info(chat.get("item"))
    lines = [_product_line(name, url)]
    buyer = _chat_buyer(chat)
    if buyer:
        lines.append(f"Покупець: {_esc(buyer)}")
    subject = _clean(chat.get("subject"))
    if subject and not name:
        lines.append(f"Тема: {_esc(subject)}")

    events = []
    block, keys, size, first = [], [], 0, ""
    for message in new:
        body = _trim(message.get("body")) or "(файл без тексту)"
        created = _clean(message.get("created"))
        piece = (f"<i>{_esc(created)}</i>\n" if created and len(new) > 1 else "") + _esc(body)
        if block and size + len(piece) > CHAT_BLOCK_LIMIT:
            events.append(_chat_event(kind_label, lines, block, keys, first))
            block, keys, size = [], [], 0
        if not block:
            first = created
        block.append(piece)
        keys.append(f"chat:{chat_id}:{message_key(message)}")
        size += len(piece)
    if block:
        events.append(_chat_event(kind_label, lines, block, keys, first))
    return events


def _chat_event(kind_label, lines, block, keys, first) -> Event:
    body_lines = []
    for index, piece in enumerate(block):
        if index:
            body_lines.append("")
        body_lines.append(piece)
    return Event(keys=list(keys), kind="chat", text=_compose(kind_label, lines, body_lines),
                 sort_key=first)


def collect_chats(client, msg_type: str, since: datetime, is_sent=None) -> list[Event]:
    events = []
    for chat in client.iter_chats(msg_type=msg_type, updated_from=since.date()):
        if isinstance(chat, dict):
            events.extend(chat_events(chat, since, client, is_sent))
    return events


# --- item comments ---------------------------------------------------------


def _comment_kind_label(comment: dict) -> str:
    if _clean(comment.get("type")).lower() == "question":
        return "Запитання під товаром"
    try:
        mark = int(comment.get("mark") or 0)
    except (TypeError, ValueError):
        mark = 0
    return f"Відгук ★{mark}" if mark > 0 else "Відгук"


def _comment_product(comment: dict) -> tuple[str, str]:
    name, url = _item_info(comment.get("item"))
    if not name:
        record = comment.get("record")
        if isinstance(record, dict):
            name = _clean(record.get("title"))
    return name, url


def comment_events(comment: dict, since: datetime) -> list[Event]:
    events = []
    comment_id = comment.get("id")
    name, url = _comment_product(comment)
    product = _product_line(name, url)
    created = _clean(comment.get("created"))

    is_ours = _is_truthy_id(comment.get("seller_id")) or _is_truthy_id(comment.get("is_market"))
    if comment_id not in (None, "") and not is_ours and _is_recent(created, since):
        body = []
        text = _trim(comment.get("text"))
        if text:
            body.append(_esc(text))
        dignity = _trim(comment.get("dignity"), 500)
        if dignity:
            body.append(f"Переваги: {_esc(dignity)}")
        shortcomings = _trim(comment.get("shortcomings"), 500)
        if shortcomings:
            body.append(f"Недоліки: {_esc(shortcomings)}")
        if body:
            lines = [product]
            buyer = _clean(comment.get("name"))
            if buyer:
                lines.append(f"Покупець: {_esc(buyer)}")
            events.append(Event(
                keys=[f"comment:{comment_id}"],
                kind="comment",
                text=_compose(_comment_kind_label(comment), lines, body),
                sort_key=created,
            ))

    for child in comment.get("children") or []:
        if not isinstance(child, dict):
            continue
        child_id = child.get("id")
        if child_id in (None, ""):
            continue
        if _is_truthy_id(child.get("seller_id")) or _is_truthy_id(child.get("is_market")):
            continue
        child_created = _clean(child.get("created"))
        if not _is_recent(child_created, since):
            continue
        text = _trim(child.get("text"))
        if not text:
            continue
        lines = [product]
        buyer = _clean(child.get("name"))
        if buyer:
            lines.append(f"Покупець: {_esc(buyer)}")
        original = _trim(comment.get("text"), 300)
        if original:
            lines.append(f"До: «{_esc(original)}»")
        events.append(Event(
            keys=[f"comment:{child_id}"],
            kind="comment",
            text=_compose("Відповідь під товаром", lines, [_esc(text)]),
            sort_key=child_created,
        ))
    return events


def collect_comments(client, since: datetime) -> list[Event]:
    events = []
    for comment in client.iter_item_comments(created_from=since.date(), expand="children"):
        if isinstance(comment, dict):
            events.extend(comment_events(comment, since))
    return events


# --- calls -----------------------------------------------------------------


def call_event(call: dict, since: datetime) -> Event | None:
    call_id = call.get("id")
    if call_id in (None, ""):
        return None
    created = _clean(call.get("date_call"))
    if not _is_recent(created, since):
        return None
    type_name = _clean(call.get("request_type_name"))
    if not type_name:
        try:
            type_name = CALL_TYPES.get(int(call.get("request_type")), "")
        except (TypeError, ValueError):
            type_name = ""
    lines = []
    if type_name:
        lines.append(f"Тема: {_esc(type_name)}")
    if call.get("order_id"):
        lines.append(f"Замовлення №{_esc(call.get('order_id'))}")
    if call.get("code_id"):
        lines.append(f"Код товару: {_esc(call.get('code_id'))}")
    buyer = _clean(call.get("user_login"))
    if buyer:
        lines.append(f"Покупець: {_esc(buyer)}")
    phone = _clean(call.get("user_phone"))
    if phone:
        lines.append(f"Телефон: {_esc(phone)}")
    text = _trim(call.get("message"))
    body = [_esc(text)] if text else []
    return Event(
        keys=[f"call:{call_id}"],
        kind="call",
        text=_compose("Звернення", lines, body),
        sort_key=created,
    )


def collect_calls(client, since: datetime) -> list[Event]:
    events = []
    for call in client.iter_calls(created_from=since.date()):
        if isinstance(call, dict):
            event = call_event(call, since)
            if event:
                events.append(event)
    return events


# --- sending ---------------------------------------------------------------


def _telegram_ready() -> bool:
    from .models import TelegramSettings

    try:
        return TelegramSettings.load().is_configured
    except Exception:
        logger.exception("rozetka messages: cannot read Telegram settings")
        return False


def _send(text: str) -> bool:
    from .telegram_utils import send_telegram_message

    return bool(send_telegram_message(text, fail_silently=True, parse_mode="HTML"))


def _mark(keys: list[str], kind: str) -> None:
    from .models import RozetkaNotice

    for key in keys:
        try:
            RozetkaNotice.objects.get_or_create(key=key[:191], defaults={"kind": kind})
        except IntegrityError:
            pass  # a parallel pass stored it first


def _is_sent(key: str) -> bool:
    from .models import RozetkaNotice

    return RozetkaNotice.objects.filter(key=key[:191]).exists()


def _already_sent(keys) -> set[str]:
    from .models import RozetkaNotice

    keys = list(keys)
    seen = set()
    for start in range(0, len(keys), 500):
        chunk = [k[:191] for k in keys[start:start + 500]]
        seen.update(RozetkaNotice.objects.filter(key__in=chunk).values_list("key", flat=True))
    return seen


def notify_new_messages(client=None) -> dict:
    result = {"sent": 0, "errors": []}
    try:
        return _notify(client, result)
    except Exception as exc:  # never raise into the poller
        logger.exception("rozetka messages pass failed")
        result["errors"].append(str(exc)[:300])
        return result


def _notify(client, result: dict) -> dict:
    if not _telegram_ready():
        return result  # nothing marked: history arrives once Telegram is set up
    if client is None:
        from .models import RozetkaSettings
        from .rozetka_api import RozetkaClient

        settings = RozetkaSettings.load()
        if not settings.is_configured:
            return result
        client = RozetkaClient(settings)

    since = rozetka_now() - timedelta(days=LOOKBACK_DAYS)
    is_sent = _is_sent
    sources = (
        ("chats-items", lambda: collect_chats(client, "items", since, is_sent)),
        ("chats-orders", lambda: collect_chats(client, "orders", since, is_sent)),
        ("comments", lambda: collect_comments(client, since)),
        ("calls", lambda: collect_calls(client, since)),
    )
    events: list[Event] = []
    for name, collect in sources:
        try:
            events.extend(collect())
        except Exception as exc:
            logger.exception("rozetka messages: %s failed", name)
            result["errors"].append(f"{name}: {str(exc)[:300]}")

    if not events:
        return result
    seen = _already_sent(k for e in events for k in e.keys)
    pending = []
    for event in events:
        if any(k[:191] in seen for k in event.keys):
            continue  # chat events are pre-filtered; this covers comments, calls, repeats
        pending.append(event)
        seen.update(k[:191] for k in event.keys)
    pending.sort(key=lambda e: e.sort_key)

    for event in pending[:MAX_TELEGRAM_PER_PASS]:
        try:
            ok = _send(event.text)
        except Exception as exc:
            logger.exception("rozetka messages: telegram send failed")
            result["errors"].append(f"telegram: {str(exc)[:200]}")
            break
        if not ok:
            result["errors"].append("telegram: повідомлення не надіслано")
            break  # Telegram is down; retry everything next pass
        _mark(event.keys, event.kind)
        result["sent"] += 1
    return result
