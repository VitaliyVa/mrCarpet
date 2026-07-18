"""Order status codes ↔ Ukrainian labels for Telegram agent."""
from __future__ import annotations

from order.models import Order

STATUS_CODES = {c[0] for c in Order.STATUS_CHOICES}
STATUS_LABEL_BY_CODE = {code: label for code, label in Order.STATUS_CHOICES}

# UA / casual aliases → code
STATUS_ALIASES = {
    "нове": "new",
    "новий": "new",
    "new": "new",
    "очікує оплати": "awaiting_payment",
    "очікує_оплати": "awaiting_payment",
    "awaiting_payment": "awaiting_payment",
    "awaiting": "awaiting_payment",
    "оплачено": "paid",
    "оплачене": "paid",
    "paid": "paid",
    "комплектується": "paid",
    "відправлено": "shipped",
    "відправл": "shipped",
    "shipped": "shipped",
    "виконано": "completed",
    "завершено": "completed",
    "completed": "completed",
    "скасовано": "cancelled",
    "відмінено": "cancelled",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def normalize_status(raw: str) -> str | None:
    key = (raw or "").strip().casefold().replace("ё", "е")
    if not key:
        return None
    if key in STATUS_ALIASES:
        return STATUS_ALIASES[key]
    if key in STATUS_CODES:
        return key
    # partial: "виконан" → completed
    for alias, code in STATUS_ALIASES.items():
        if len(alias) >= 4 and (alias in key or key in alias):
            return code
    return None


def status_list_reply() -> str:
    lines = ["Статуси замовлення (пиши українською або кодом):"]
    for code, label in Order.STATUS_CHOICES:
        lines.append(f"• {label} — {code}")
    lines.append(
        "\nПриклад: «містер карпет, в замовленні №… зміни статус на Виконано і напиши клієнту лист»"
    )
    return "\n".join(lines)


def default_status_email(order_number: int, status: str, *, customer_name: str = "") -> tuple[str, str]:
    label = STATUS_LABEL_BY_CODE.get(status, status)
    name = (customer_name or "").strip() or "клієнте"
    subject = f"Оновлення замовлення №{order_number} — {label}"
    body = (
        f"Доброго дня, {name}!\n\n"
        f"Статус вашого замовлення №{order_number} змінено на: {label}.\n\n"
        f"З повагою,\nмагазин mr.Carpet\nhttps://mrcarpet24.com/"
    )
    return subject, body
