"""Resolve first product size for interior (scene) generation prompts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from catalog.models import Product
from catalog.services.parse_size import SizeParseError, parse_size_label


class SceneSizeError(ValueError):
    """No usable size for scene generation."""


@dataclass(frozen=True)
class SceneSizeInfo:
    label: str
    width_m: Decimal
    length_m: Decimal
    source: str  # "db" | "request"

    @property
    def is_round(self) -> bool:
        return self.width_m == self.length_m


def get_first_product_size_label(product: Product) -> str | None:
    """First variation with a non-empty Size.title (same idea as product_attr.first)."""
    attr = (
        product.product_attr.filter(size__isnull=False)
        .exclude(size__title__isnull=True)
        .exclude(size__title="")
        .select_related("size")
        .order_by("pk")
        .first()
    )
    if not attr or not attr.size:
        return None
    label = (attr.size.title or "").strip()
    return label or None


def resolve_scene_size(
    *,
    product_id: str | int | None = None,
    size_label: str | None = None,
) -> SceneSizeInfo:
    """
    Prefer first saved ProductAttribute.size from DB (by product_id).
    Fallback: size_label from the admin form (unsaved inline).
    """
    label: str | None = None
    source = "request"

    if product_id not in (None, ""):
        try:
            pid = int(product_id)
        except (TypeError, ValueError) as exc:
            raise SceneSizeError("Невірний product_id") from exc
        try:
            product = Product.admin_objects.get(pk=pid)
        except Product.DoesNotExist as exc:
            raise SceneSizeError(f"Товар #{pid} не знайдено") from exc
        label = get_first_product_size_label(product)
        if label:
            source = "db"

    if not label:
        label = (size_label or "").strip() or None
        source = "request"

    if not label:
        raise SceneSizeError(
            "Для генерації інтер'єру потрібен хоча б один розмір у «Варіації → Розмір». "
            "Додайте розмір і збережіть товар."
        )

    try:
        width_m, length_m = parse_size_label(label)
    except SizeParseError as exc:
        raise SceneSizeError(
            f"Не вдалося розпізнати розмір {label!r}: {exc}. "
            "Очікувано формат на кшталт 1.5x2.3 або Ø 67 см."
        ) from exc

    return SceneSizeInfo(
        label=label,
        width_m=width_m,
        length_m=length_m,
        source=source,
    )
