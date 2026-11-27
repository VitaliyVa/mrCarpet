"""Shipping weight and package size for the Rozetka feed («Вага», «Габарити
упаковки»), needed for Rozetka Smart and delivery.

We have no weighed data in the DB, so the numbers come from published
weights of the same collections / product types (research 27.11.2026, mostly
Epicentr cards with their own logistics, see docs/marketplaces.md):

- Karat Mira 1.52 kg/m² (80x150 1.78, 160x230 5.59, 200x300 9.12 kg),
  Oksi 1.30-1.52, Gold 1.35, Fashion ~1.8, Lotos 1.83, Itea 1.80,
  Cappuccino 1.70, Kolibri 2.30, Fantasy (shaggy) 2.60;
- Karat Flex on rubber 1.5 (50x80 0.6, 133x195 3.95, 200x300 9.12 kg);
- rubber-backed door mats ~2.0, bath mats on rubber ~1.8, solid rubber
  door mats ~5 (40x60 ≈ 1.2 kg);
- Turkish PP on jute: 6.5 mm ~1.5, 10 mm ~2.1, kids 4 mm ~1.2.

Weight = full rectangle area (ovals/semicircles are overestimated on
purpose) x kg/m² x 1.1 (film, tape, safety), rounded up to 0.1 kg.

Packing: small rubber-backed mats go flat; everything else is a roll whose
length is the short side + 3 cm (Epicentr: 80x150 -> 800 mm, 200x300 ->
2000 mm) and whose diameter follows D = sqrt(4·t·L/π) + 2 cm, L the long
side, t the effective rolled thickness (calibrated on Mira 200x300 ≈ 15-18 cm).
"""

from __future__ import annotations

import math
import re

from project.merchant_feed import size_dimensions

MARGIN = 1.1
FLAT_MAX_AREA_M2 = 0.9
FLAT_HEIGHT_CM = 3
ROLL_EXTRA_CM = 3
FILM_CM = 2

# (title regex, kg/m², effective rolled thickness mm); first match wins.
_COLLECTIONS = (
    (r"\bfantasy\b", 2.6, 13.0),
    (r"\bkolibri\b", 2.3, 8.0),
    (r"\blotos\b", 1.85, 8.0),
    (r"\bitea\b", 1.8, 8.0),
    (r"\bfashion\b", 1.8, 8.0),
    (r"\bcappuccino\b", 1.7, 7.0),
    (r"\bmira\b|\boksi\b|\bgold\b", 1.55, 6.5),
    (r"\bflex\b", 1.5, 4.0),
)


def _pile_mm(value: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*мм", value or "")
    return float(match.group(1).replace(",", ".")) if match else None


def product_kind(title: str, params: dict) -> tuple[float, float, bool]:
    """(kg/m², rolled thickness mm, can ship flat) for one product."""
    lower = (title or "").lower()
    base = (params.get("Основа") or "").lower()
    material = (params.get("Матеріал") or "").lower()
    rubber_base = base in ("гума", "резина")
    for pattern, kg, thickness in _COLLECTIONS:
        if re.search(pattern, lower):
            return kg, thickness, rubber_base
    if material == "гума":  # solid rubber door mat
        return 5.0, 8.0, True
    if rubber_base:
        if "ванн" in lower or _pile_mm(params.get("Висота ворсу", "")):
            return 1.8, 7.0, True  # pile bath mats / Estera on rubber
        if "двер" in lower:
            return 2.0, 5.0, True
        return 1.5, 4.0, True  # kitchen / flat-woven on rubber
    pile = _pile_mm(params.get("Висота ворсу", ""))
    if pile is None:
        return 1.5, 5.0, False  # flat-woven on jute
    if pile >= 20:
        return 2.6, 13.0, False
    if pile >= 9:
        return 2.1, 8.5, False
    if pile <= 4.5:
        return 1.2, 4.5, False
    return 1.55, 6.5, False


def _ceil(value: float, step: float) -> float:
    return math.ceil(round(value / step, 6)) * step


def _metres(cm: float) -> str:
    return f"{cm / 100:.2f}".rstrip("0").rstrip(".")


def logistics(title: str, size: str, params: dict) -> dict | None:
    """{"weight_kg", "package": (a, b, c) cm, "package_text", "weight_text",
    "roll_length_cm"} or None when the size is unknown."""
    dims = size_dimensions(size)
    if not dims:
        return None
    width, length = sorted(dims)
    area = width * length / 10000
    kg_m2, thickness, can_be_flat = product_kind(title, params)
    weight = max(_ceil(area * kg_m2 * MARGIN, 0.1), 0.2)
    if can_be_flat and area <= FLAT_MAX_AREA_M2:
        package = (FLAT_HEIGHT_CM, width, length)
        roll_length = length
    else:
        roll_length = width + ROLL_EXTRA_CM
        diameter_mm = math.sqrt(4 * thickness * length * 10 / math.pi)
        diameter = _ceil(diameter_mm / 10 + FILM_CM, 1)
        package = (diameter, diameter, roll_length)
    return {
        "weight_kg": round(weight, 1),
        "weight_text": f"{weight:.1f} кг",
        "package": package,
        "package_text": "x".join(_metres(v) for v in package) + " м",
        "roll_length_cm": roll_length,
    }
