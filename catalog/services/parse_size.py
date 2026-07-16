"""Parse product size labels like '1.0x2.0', '2.0х4.0', '1,5×2' into metres."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Latin x, Cyrillic х, multiplication sign, asterisk
_SIZE_SPLIT = re.compile(r"\s*[xх×*X]\s*", re.UNICODE)
_NON_NUM = re.compile(r"[^\d.,]+")


class SizeParseError(ValueError):
    pass


def _to_decimal(raw: str) -> Decimal:
    cleaned = _NON_NUM.sub("", raw.strip()).replace(",", ".")
    if not cleaned:
        raise SizeParseError(f"Порожнє число розміру: {raw!r}")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise SizeParseError(f"Невірне число розміру: {raw!r}") from exc
    if value <= 0:
        raise SizeParseError(f"Розмір має бути > 0: {value}")
    if value > 50:
        raise SizeParseError(f"Розмір занадто великий: {value}")
    return value


def parse_size_label(label: str) -> tuple[Decimal, Decimal]:
    """
    Return (width_m, length_m) from a size chip label.

    Accepts: 1.0x2.0 | 2.0х4.0 | 1,5×2 | 1.0 x 2.0 м
    """
    if not label or not str(label).strip():
        raise SizeParseError("Порожній розмір")

    text = str(label).strip()
    text = re.sub(r"\s*[мmМ]\.?\s*$", "", text, flags=re.IGNORECASE)

    parts = _SIZE_SPLIT.split(text, maxsplit=1)
    if len(parts) != 2:
        raise SizeParseError(f"Очікувано WxL, отримано: {label!r}")

    width = _to_decimal(parts[0])
    length = _to_decimal(parts[1])
    return width, length


def normalize_size_key(width: Decimal | float | str, length: Decimal | float | str) -> str:
    """Filesystem-safe key: 1.00x2.00"""
    w = Decimal(str(width)).quantize(Decimal("0.01"))
    l = Decimal(str(length)).quantize(Decimal("0.01"))
    return f"{w}x{l}"
