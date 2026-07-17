"""Sort product size variations by first numeric value in Size.title (width)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from catalog.models import Product, ProductAttribute

_FIRST_NUM = re.compile(r"([\d]+(?:[.,]\d+)?)")


def size_first_number(label: str | None) -> Decimal | None:
    """First number in a size label: '100x200' → 100, '1,5x2' → 1.5, '∅ 67 см' → 67."""
    if not label or not str(label).strip():
        return None
    match = _FIRST_NUM.search(str(label))
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None


def product_attr_sort_key(attr: ProductAttribute) -> tuple:
    """
    Sort: fixed sizes by width asc, then unparseable labels, then custom.
    Stable tie-break by pk.
    """
    custom = 1 if attr.custom_attribute else 0
    size = getattr(attr, "size", None) if attr.size_id else None
    label = (size.title or "") if size is not None else ""
    width = size_first_number(label)
    if width is None and attr.custom_attribute and attr.min_len is not None:
        width = Decimal(str(attr.min_len))
    return (custom, width is None, width if width is not None else Decimal(0), attr.pk or 0)


def reorder_product_attributes(product: Product) -> int:
    """
    Assign sort_order = 10, 20, 30… by width (first number in size).
    Uses QuerySet.update to avoid ProductAttribute.save() side effects.
    Returns number of rows whose sort_order changed.
    """
    from catalog.models import ProductAttribute

    attrs = list(product.product_attr.select_related("size"))
    attrs.sort(key=product_attr_sort_key)
    changed = 0
    for index, attr in enumerate(attrs):
        new_order = (index + 1) * 10
        if attr.sort_order != new_order:
            ProductAttribute.objects.filter(pk=attr.pk).update(sort_order=new_order)
            changed += 1
    return changed
