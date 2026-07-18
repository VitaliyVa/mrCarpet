"""Cheap intent router — skip LLM for obvious shop questions."""
from __future__ import annotations

import re

from .product_resolve import PRODUCT_URL_RE, extract_size_from_text

# LLM sometimes narrates tools instead of returning type=tool
_FAKE_TOOL_REPLY = re.compile(
    r"(виконуємо|виконую|виконаю|запускаю|calling|running)\s+"
    r"(команду\s+)?(?P<name>count_orders|list_recent_orders|get_order|"
    r"count_products|count_in_stock_products|get_product_stock|"
    r"set_order_status|send_order_email|change_stock_quantity)",
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
    "• скільки замовлень (усіх / нових)\n"
    "• останні замовлення\n"
    "• деталі замовлення за номером\n"
    "• скільки товарів на сайті / в наявності\n"
    "• залишки конкретного килима\n\n"
    "З підтвердженням кнопкою в чаті:\n"
    "• змінити статус замовлення\n"
    "• надіслати лист клієнту\n"
    "• змінити кількість на складі (за посиланням або назвою + розмір)\n\n"
    "Приклади:\n"
    "• містер карпет, скільки замовлень?\n"
    "• https://mrcarpet24.com/catalog/product/.../ розмір 0.8х1.5 постав 5\n"
    "• Килим … 0.8х1.5 +2\n\n"
    "Звертайся: «містер карпет, …», @бот або reply на моє повідомлення.\n"
    "Пам’ять: тримаю короткий контекст діалогу (останні репліки + summary)."
)


def _parse_stock_change(text: str) -> dict | None:
    """
    Detect set/delta quantity for a product from URL or free text.
    Returns write plan args or None.
    """
    raw = text or ""
    t = raw.casefold()
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

    # Need a product signal: URL, or title-ish + size, or explicit stock words
    stockish = bool(
        re.search(r"(склад|залиш|кількіст|наявніст|шт\b|штук)", t)
        or has_url
        or size
    )
    if not stockish:
        return None

    url_m = PRODUCT_URL_RE.search(raw)
    url = url_m.group(0) if url_m else ""
    # absolute URL if relative matched poorly
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


def maybe_direct_plan(user_text: str) -> dict | None:
    t = (user_text or "").casefold()

    if re.search(
        r"(що\s+ти\s+вмієш|що\s+вмієш|help|допомог|команди|можливост)",
        t,
    ):
        return {"type": "reply", "text": HELP_REPLY}

    stock_plan = _parse_stock_change(user_text or "")
    if stock_plan:
        return stock_plan

    if re.search(r"скільки.{0,40}замовлен", t) or re.search(
        r"кількість.{0,40}замовлен", t
    ):
        if re.search(r"\bнов", t) and "статус" not in t:
            return {"type": "tool", "name": "count_orders", "args": {"status": "new"}}
        return {"type": "tool", "name": "count_orders", "args": {}}

    if re.search(r"останн\w*.{0,20}замовлен", t) or "list orders" in t:
        return {"type": "tool", "name": "list_recent_orders", "args": {"limit": 5}}

    if re.search(r"скільки.{0,40}(товар|килим)", t):
        if "наявност" in t or "склад" in t or "в наявност" in t:
            return {"type": "tool", "name": "count_in_stock_products", "args": {}}
        return {"type": "tool", "name": "count_products", "args": {}}

    # stock lookup by URL alone
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

    m2 = re.search(r"замовлення\s*№?\s*(\d{6,})", t)
    if m2:
        return {
            "type": "tool",
            "name": "get_order",
            "args": {"order_number": int(m2.group(1))},
        }

    m3 = re.search(
        r"статус\s+замовлення\s*№?\s*(\d{6,})\s+(?:на|→|->|в)?\s*"
        r"(new|awaiting_payment|paid|shipped|completed|cancelled|"
        r"нове|відправлено|виконано|скасовано|оплачено)",
        t,
    )
    if m3:
        status_map = {
            "нове": "new",
            "відправлено": "shipped",
            "виконано": "completed",
            "скасовано": "cancelled",
            "оплачено": "paid",
        }
        st = m3.group(2)
        st = status_map.get(st, st)
        return {
            "type": "write",
            "name": "set_order_status",
            "args": {"order_number": int(m3.group(1)), "status": st},
        }

    return None
