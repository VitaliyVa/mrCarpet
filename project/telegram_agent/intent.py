"""Cheap intent router — skip LLM for obvious shop questions."""
from __future__ import annotations

import re

# LLM sometimes narrates tools instead of returning type=tool
_FAKE_TOOL_REPLY = re.compile(
    r"(виконуємо|виконую|виконаю|запускаю|calling|running)\s+"
    r"(команду\s+)?(?P<name>count_orders|list_recent_orders|get_order|"
    r"count_products|count_in_stock_products|get_product_stock|"
    r"set_order_status|send_order_email)",
    re.I,
)


def fake_tool_narration_plan(reply_text: str) -> dict | None:
    """If model said 'executing count_orders...' — convert to real tool plan."""
    m = _FAKE_TOOL_REPLY.search(reply_text or "")
    if not m:
        return None
    name = m.group("name")
    return {"type": "tool", "name": name, "args": {}}


def maybe_direct_plan(user_text: str) -> dict | None:
    t = (user_text or "").casefold()

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

    m = re.search(
        r"(?:наявність|залишок|скільки)\s+(?:у|для|по)?\s*[«\"]?(.+?)[»\"]?\s*$",
        t,
    )
    if m and len(m.group(1).strip()) >= 3:
        q = m.group(1).strip(" «»\"'")
        # avoid catching whole wake sentence
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
