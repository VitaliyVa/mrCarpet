"""Parse product size labels like '1.0x2.0', '2.0х4.0', '∅ 67 см' into metres."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Latin x, Cyrillic х, multiplication sign, asterisk
_SIZE_SPLIT = re.compile(r"\s*[xх×*X]\s*", re.UNICODE)
_NON_NUM = re.compile(r"[^\d.,]+")
# ∅ (often used), Ø, ⌀ (true diameter) — optional symbol
_DIAMETER_MARKED = re.compile(
    r"^[∅Ø⌀]\s*([\d.,]+)\s*(см|cm|м|m)?\.?\s*$",
    re.IGNORECASE | re.UNICODE,
)
# Round size without symbol: "67 см", "80см" (must have см/cm — avoids ambiguity)
_DIAMETER_CM = re.compile(
    r"^([\d.,]+)\s*(см|cm)\.?\s*$",
    re.IGNORECASE | re.UNICODE,
)
_MAX_M = Decimal("50")


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
    return value


def _validate_metres(value: Decimal) -> Decimal:
    if value <= 0:
        raise SizeParseError(f"Розмір має бути > 0: {value}")
    if value > _MAX_M:
        raise SizeParseError(f"Розмір занадто великий: {value}")
    return value


def _diameter_to_metres(raw_num: str, unit: str | None) -> Decimal:
    """Round-rug diameter → metres. Catalog uses cm (∅ 67 см); м also accepted."""
    value = _to_decimal(raw_num)
    u = (unit or "").lower()
    if u in ("см", "cm"):
        metres = value / Decimal("100")
    elif u in ("м", "m"):
        metres = value
    elif value >= 10:
        # Bare number after ∅ is almost always centimetres in this catalog
        metres = value / Decimal("100")
    else:
        metres = value
    return _validate_metres(metres)


def parse_size_label(label: str) -> tuple[Decimal, Decimal]:
    """
    Return (width_m, length_m) from a size chip label.

    Accepts:
    - WxL: 1.0x2.0 | 2.0х4.0 | 1,5×2 | 1.0 x 2.0 м
    - Round diameter: ∅ 67 см | Ø67см | ⌀ 1.5 м | 67 см | 80см → square (d, d) in metres
    """
    if not label or not str(label).strip():
        raise SizeParseError("Порожній розмір")

    text = str(label).strip()

    diam = _DIAMETER_MARKED.match(text) or _DIAMETER_CM.match(text)
    if diam:
        metres = _diameter_to_metres(diam.group(1), diam.group(2))
        return metres, metres

    text = re.sub(r"\s*[мmМ]\.?\s*$", "", text, flags=re.IGNORECASE)

    parts = _SIZE_SPLIT.split(text, maxsplit=1)
    if len(parts) != 2:
        raise SizeParseError(f"Очікувано WxL або діаметр (∅ N см / N см), отримано: {label!r}")

    width = _validate_metres(_to_decimal(parts[0]))
    length = _validate_metres(_to_decimal(parts[1]))
    return width, length


def normalize_size_key(width: Decimal | float | str, length: Decimal | float | str) -> str:
    """Filesystem-safe key: 1.00x2.00"""
    w = Decimal(str(width)).quantize(Decimal("0.01"))
    l = Decimal(str(length)).quantize(Decimal("0.01"))
    return f"{w}x{l}"
