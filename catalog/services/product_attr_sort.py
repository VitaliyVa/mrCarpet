"""Sort product size variations / Size choices by first numeric value in title (width)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.db.models import Case, IntegerField, QuerySet, Value, When

if TYPE_CHECKING:
    from catalog.models import Product, ProductAttribute, Size

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


def size_model_sort_key(size: Size) -> tuple:
    """Sort Size rows: numeric width asc, then labels without numbers, then title/pk."""
    width = size_first_number(size.title)
    return (
        width is None,
        width if width is not None else Decimal(0),
        (size.title or "").casefold(),
        size.pk or 0,
    )


def ordered_size_queryset(queryset: QuerySet | None = None) -> QuerySet:
    """
    Size queryset ordered by width (first number in title).
    Used for admin FK selects so managers can find 50x50 before 300x300.
    """
    from catalog.models import Size

    qs = Size.objects.all() if queryset is None else queryset
    sizes = sorted(qs, key=size_model_sort_key)
    if not sizes:
        return qs.none()

    pk_order = [s.pk for s in sizes]
    preserved = Case(
        *[When(pk=pk, then=Value(index)) for index, pk in enumerate(pk_order)],
        output_field=IntegerField(),
    )
    return (
        qs.model.objects.filter(pk__in=pk_order)
        .annotate(_size_width_order=preserved)
        .order_by("_size_width_order")
    )


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
