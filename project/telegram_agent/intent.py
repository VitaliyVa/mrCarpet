"""Cheap intent router — skip LLM for obvious shop questions."""
from __future__ import annotations

import re

from .product_resolve import PRODUCT_URL_RE, extract_size_from_text
from .status_labels import (
    default_status_email,
    normalize_status,
    status_list_reply,
)

# LLM sometimes narrates tools instead of returning type=tool
_FAKE_TOOL_REPLY = re.compile(
    r"(виконуємо|виконую|виконаю|запускаю|calling|running)\s+"
    r"(команду\s+)?(?P<name>count_orders|list_recent_orders|get_order|"
    r"find_orders|count_products|count_in_stock_products|get_product_stock|"
    r"get_ga4_report|"
    r"set_order_status|send_order_email|change_stock_quantity)",
    re.I,
)

_ANALYTICS_RE = re.compile(
    r"(аналітик|analytics|га4|ga4|воронк|трафік|трафик|realtime|"
    r"real[\s-]?time|звіт\s+ga|покажи\s+(статистик|метрики)|"
    r"статистик\w*\s+(сайт|га|ga)|dashboard)",
    re.I,
)


# Asking about the networks specifically. Deliberately narrower than a bare
# "соцмереж": that word turns up in ordinary talk about posting more often,
# and answering it with a chart album would be noise. An analytics word has
# to appear alongside it, on either side.
_SOCIAL_RE = re.compile(
    r"((аналітик|статистик|метрик|показник|звіт|результат)\w*\s+"
    r"(по\s+|з\s+)?(соц|мереж|instagram|інстаграм|tiktok|тікток|youtube|ютуб)"
    r"|(соц\.?\s*мереж|соцмереж)\w*\s*"
    r"(аналітик|статистик|метрик|показник|звіт|результат)"
    r"|скільки\s+(переглядів|людей)\s+(подивил|побачил|переглянул))",
    re.I,
)


def _analytics_days(text: str) -> int:
    t = (text or "").casefold()
    if re.search(r"(сьогодні|today|1\s*дн)", t):
        return 1
    if re.search(r"(місяц|month|30\s*дн)", t):
        return 30
    if re.search(r"(2\s*тиж|14\s*дн)", t):
        return 14
    m = re.search(r"за\s+(\d{1,2})\s*дн", t)
    if m:
        try:
            return max(1, min(int(m.group(1)), 30))
        except ValueError:
            pass
    return 7


def _analytics_report(text: str) -> str:
    t = (text or "").casefold()
    if re.search(r"realtime|real[\s-]?time|зараз\s+на\s+сайт|онлайн\s+зараз", t):
        return "realtime"
    if re.search(r"воронк|ecommerce|e-?commerce|покупк", t) and not re.search(
        r"аналітик|dashboard|трафік", t
    ):
        # "воронка" alone → ecommerce; "аналітика" → full dashboard
        if re.search(r"воронк", t):
            return "ecommerce"
    return "dashboard"

_ORDER_NUM_RE = re.compile(
    r"(?:замовлення\s*)?№\s*(\d{6,})|(?:order\s*#?\s*|замовлен\w*\s+)(\d{6,})",
    re.I,
)

_STATUS_TOKEN_RE = re.compile(
    r"(new|awaiting_payment|paid|shipped|completed|cancelled|canceled|"
    r"нове|новий|оплачено|оплачене|відправлено|виконано|завершено|"
    r"скасовано|відмінено|очікує\s+оплати)",
    re.I,
)

_WANTS_EMAIL_RE = re.compile(
    r"(напиш\w*.{0,20}(лист|email|пошт)|"
    r"надісл\w*.{0,20}(лист|email|пошт)|"
    r"(лист|email|листа)\s+(клієнт|покупц)|"
    r"повідом\w*\s+клієнт)",
    re.I,
)

_ORDER_STATUS_CTX_RE = re.compile(
    r"\bстатус\b|\bcompleted\b|\bshipped\b|\bcancelled\b|\bawaiting_payment\b",
    re.I,
)


def fake_tool_narration_plan(reply_text: str) -> dict | None:
    """If model said 'executing count_orders...' — convert to real tool plan."""
    m = _FAKE_TOOL_REPLY.search(reply_text or "")
    if not m:
        return None
    name = m.group("name")
    return {"type": "tool", "name": name, "args": {}}


HELP_REPLY = (
    "Я містер Карпет — помічник магазину в цій групі.\n\n"
    "Можу розказати:\n"
    "• скільки замовлень (усіх / нових / очікують оплати)\n"
    "• останні замовлення\n"
    "• деталі замовлення за номером\n"
    "• пошук замовлення за телефоном / ім'ям\n"
    "• які є статуси замовлення\n"
    "• скільки товарів на сайті / в наявності\n"
    "• залишки конкретного килима\n"
    "• аналітика GA4 (воронка, трафік, KPI) — графіки в чат\n\n"
    "З підтвердженням кнопкою в чаті:\n"
    "• змінити статус замовлення\n"
    "• надіслати лист клієнту\n"
    "• змінити кількість на складі (за посиланням або назвою + розмір)\n\n"
    "Приклади:\n"
    "• містер карпет, скільки замовлень?\n"
    "• містер карпет, покажи аналітику\n"
    "• містер карпет, воронка за 14 днів\n"
    "• містер карпет, realtime\n"
    "• містер карпет, які є статуси?\n"
    "• знайди замовлення по телефону 0501234567\n"
    "• в замовленні №… зміни статус на Виконано і напиши клієнту лист\n"
    "• https://mrcarpet24.com/catalog/product/.../ розмір 0.8х1.5 постав 5\n\n"
    "Звертайся: «містер карпет, …», @бот або reply на моє повідомлення.\n"
    "Пам’ять: тримаю короткий контекст діалогу (останні репліки + summary)."
)

_PHONE_RE = re.compile(
    r"(?:\+?38)?0\d{9}"
    r"|(?:\+?380\d{9})"
    r"|(?<!\d)0\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)",
)


def extract_order_number(*texts: str) -> int | None:
    for text in texts:
        if not text:
            continue
        m = _ORDER_NUM_RE.search(text)
        if not m:
            # bare long number near «замовлен»
            m2 = re.search(r"замовлен\w*.{0,40}?(\d{10,})", text, re.I)
            if m2:
                return int(m2.group(1))
            continue
        num = m.group(1) or m.group(2)
        if num:
            return int(num)
    return None


def _wants_email(text: str) -> bool:
    return bool(_WANTS_EMAIL_RE.search(text or ""))


def _extract_status_token(text: str) -> str | None:
    m = _STATUS_TOKEN_RE.search(text or "")
    if not m:
        return None
    return normalize_status(m.group(0))


def _parse_stock_change(text: str) -> dict | None:
    """
    Detect set/delta quantity for a product from URL or free text.
    Returns write plan args or None.
    """
    raw = text or ""
    t = raw.casefold()

    # Never hijack order-status / email requests as stock changes
    if _ORDER_STATUS_CTX_RE.search(raw) and not re.search(
        r"(склад|залиш|кількіст\w*\s+на\s+склад)", t
    ):
        return None
    if _wants_email(raw) and "статус" in t:
        return None

    has_url = bool(PRODUCT_URL_RE.search(raw))
    size = extract_size_from_text(raw)

    mode = None
    value = None

    m = re.search(r"(?:постав|зроби|встанови|set)\s+(\d+)\b", t)
    if m:
        mode, value = "set", int(m.group(1))
    if mode is None:
        m = re.search(r"(?:збільш\w*|додай|плюс)\s*(?:на\s+)?(\d+)\b", t)
        if m:
            mode, value = "delta", int(m.group(1))
    if mode is None:
        m = re.search(r"(?:зменш\w*|відніми|мінус)\s*(?:на\s+)?(\d+)\b", t)
        if m:
            mode, value = "delta", -int(m.group(1))
    if mode is None:
        m = re.search(r"(?<!\d)([+\-])\s*(\d+)\b", raw)
        if m:
            sign = 1 if m.group(1) == "+" else -1
            mode, value = "delta", sign * int(m.group(2))

    if mode is None or value is None:
        return None

    stockish = bool(
        re.search(r"(склад|залиш|кількіст|наявніст|шт\b|штук)", t)
        or has_url
        or size
    )
    if not stockish:
        return None

    url_m = PRODUCT_URL_RE.search(raw)
    url = url_m.group(0) if url_m else ""
    if url and not url.startswith("http"):
        abs_m = re.search(r"https?://[^\s]+/catalog/product/[\w\-]+/?", raw, re.I)
        if abs_m:
            url = abs_m.group(0)

    args = {
        "mode": mode,
        "value": value,
        "url": url,
        "query": raw if not url else "",
        "size": size or "",
    }
    return {
        "type": "write",
        "name": "change_stock_quantity",
        "args": args,
    }


def _status_change_plan(user_text: str, *, context_text: str = "") -> dict | None:
    """
    Detect order status change (+ optional email) from text / reply context.
    """
    raw = user_text or ""
    t = raw.casefold()
    if "статус" not in t and not re.search(
        r"(зміни|постав|поставте|зроби).{0,30}(completed|виконано|shipped|відправлено)",
        t,
    ):
        return None

    # Must look like a change request, not "які є статуси?"
    if re.search(r"як(і|ий)\s+(є\s+)?статус", t) and not re.search(
        r"(зміни|постав|зроби|на\s+статус)", t
    ):
        return None

    status = _extract_status_token(raw)
    if not status:
        return None

    # Prefer explicit change phrasing
    changing = bool(
        re.search(
            r"(зміни|поміняй|постав|зроби|онови|переведи|став|на\s+статус|"
            r"статус\s+на|→|->)",
            t,
        )
    )
    if not changing:
        return None

    order_number = extract_order_number(raw, context_text)
    if not order_number:
        return None

    calls = [
        {
            "name": "set_order_status",
            "args": {"order_number": order_number, "status": status},
        }
    ]
    if _wants_email(raw):
        customer = ""
        try:
            from order.models import Order

            order = Order.objects.filter(order_number=order_number).first()
            if order:
                customer = f"{order.name} {order.surname}".strip()
        except Exception:
            pass
        subject, body = default_status_email(
            order_number, status, customer_name=customer
        )
        calls.append(
            {
                "name": "send_order_email",
                "args": {
                    "order_number": order_number,
                    "subject": subject,
                    "body": body,
                },
            }
        )

    if len(calls) == 1:
        return {"type": "write", "name": calls[0]["name"], "args": calls[0]["args"]}
    return {"type": "tools", "calls": calls}


def maybe_direct_plan(user_text: str, *, context_text: str = "") -> dict | None:
    t = (user_text or "").casefold()

    if re.search(
        r"(що\s+ти\s+вмієш|що\s+вмієш|help|допомог|команди|можливост)",
        t,
    ):
        return {"type": "reply", "text": HELP_REPLY}

    # "який статус у замовленні №…" → current status via get_order
    # (must run BEFORE the statuses catalog reply)
    order_number_early = extract_order_number(user_text or "", context_text or "")
    asks_current_status = bool(
        re.search(
            r"(як(ий|а|е)\s+(зараз\s+)?статус|"
            r"статус\s+(цього\s+|у\s+|в\s+)?замовлен|"
            r"в\s+якому\s+статус|"
            r"який\s+статус\s+(в|у|замовлен))",
            t,
        )
    )
    if (
        order_number_early
        and asks_current_status
        and not re.search(r"(зміни|постав|зроби|на\s+статус\s+\w|список)", t)
    ):
        return {
            "type": "tool",
            "name": "get_order",
            "args": {"order_number": order_number_early},
        }

    # List statuses catalog — only when NOT asking about a specific order
    if (
        re.search(
            r"(як(і|ий)\s+(є\s+)?статус|список\s+статус|які\s+статус|"
            r"status(es)?\s*\?|what\s+statuses)",
            t,
        )
        and not order_number_early
        and not re.search(r"замовлен", t)
        and not re.search(r"(зміни|постав|зроби|на\s+статус\s+\w)", t)
    ):
        return {"type": "reply", "text": status_list_reply()}

    # Order status change (+ email) before stock — avoids context bleed
    status_plan = _status_change_plan(user_text or "", context_text=context_text or "")
    if status_plan:
        return status_plan

    stock_plan = _parse_stock_change(user_text or "")
    if stock_plan:
        return stock_plan

    # Social networks only — before the GA4 branch, which "аналітика" would
    # otherwise claim first and answer with the whole album.
    if _SOCIAL_RE.search(t):
        return {
            "type": "tool",
            "name": "get_ga4_report",
            "args": {"days": _analytics_days(user_text or ""), "report": "social"},
        }

    # GA4 analytics (charts) — before order lookups that match «покажи»
    if _ANALYTICS_RE.search(t) or re.search(
        r"покажи\s+(аналітик|статистик|воронк|трафік|ga4|га4)", t
    ):
        return {
            "type": "tool",
            "name": "get_ga4_report",
            "args": {
                "days": _analytics_days(user_text or ""),
                "report": _analytics_report(user_text or ""),
            },
        }

    if re.search(r"скільки.{0,40}замовлен", t) or re.search(
        r"кількість.{0,40}замовлен", t
    ):
        if re.search(r"\bнов", t) and "статус" not in t:
            return {"type": "tool", "name": "count_orders", "args": {"status": "new"}}
        return {"type": "tool", "name": "count_orders", "args": {}}

    if re.search(
        r"(очіку\w*\s+оплати|неоплачен|awaiting_payment|не\s+оплачен)",
        t,
    ) and re.search(r"замовлен", t):
        return {
            "type": "tool",
            "name": "list_recent_orders",
            "args": {"limit": 8, "status": "awaiting_payment"},
        }

    if re.search(r"останн\w*.{0,20}замовлен", t) or "list orders" in t:
        return {"type": "tool", "name": "list_recent_orders", "args": {"limit": 5}}

    # Find by phone / name
    phone_m = _PHONE_RE.search(user_text or "")
    if phone_m and re.search(r"(замовлен|знайд|пошук|телефон|номер)", t):
        digits = re.sub(r"\D+", "", phone_m.group(0))
        return {
            "type": "tool",
            "name": "find_orders",
            "args": {"phone": digits, "limit": 5},
        }
    m_find = re.search(
        r"(?:знайд\w*|пошук|шукай)\s+замовлен\w*.{0,20}"
        r"(?:по|за)?\s*(?:ім.?ям|прізвищ|клієнт)?\s*[«\"]?(.+?)[»\"]?\s*$",
        t,
    )
    if m_find and len(m_find.group(1).strip()) >= 2:
        return {
            "type": "tool",
            "name": "find_orders",
            "args": {"query": m_find.group(1).strip(" «»\"'"), "limit": 5},
        }

    if re.search(r"скільки.{0,40}(товар|килим)", t):
        if "наявност" in t or "склад" in t or "в наявност" in t:
            return {"type": "tool", "name": "count_in_stock_products", "args": {}}
        return {"type": "tool", "name": "count_products", "args": {}}

    if PRODUCT_URL_RE.search(user_text or "") and not _parse_stock_change(user_text or ""):
        return {
            "type": "tool",
            "name": "get_product_stock",
            "args": {"query": user_text},
        }

    m = re.search(
        r"(?:наявність|залишок|скільки)\s+(?:у|для|по)?\s*[«\"]?(.+?)[»\"]?\s*$",
        t,
    )
    if m and len(m.group(1).strip()) >= 3:
        q = m.group(1).strip(" «»\"'")
        if "карпет" not in q and "замовлен" not in q:
            return {"type": "tool", "name": "get_product_stock", "args": {"query": q}}

    # Order lookup — number from text or reply/history context
    order_number = extract_order_number(user_text or "", context_text or "")
    wants_lookup = bool(
        re.search(r"(замовлен|детал|покаж|покажи|що\s+там|інфо|статус)", t)
    )
    if (
        order_number
        and wants_lookup
        and not re.search(r"(зміни|постав|зроби|напиш)", t)
    ):
        return {
            "type": "tool",
            "name": "get_order",
            "args": {"order_number": order_number},
        }

    return None
