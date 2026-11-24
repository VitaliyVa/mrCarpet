"""Default order of product listings (category, collection, home).

Why: the plain manager order is "in stock first, then newest". When a batch
of one kind of product is added at once (12 bath mats 60x100), that batch
fills page 1 of «Турецькі» and «Вся колекція», and a shopper who came for
rugs sees bath mats only (audit 24.11.2026, C1/T4).

How (one SQL query, no new fields, deterministic):

1. In stock before out of stock (unchanged).
2. "Weak" cards (title with «без назви», placeholder photo) after the rest
   of their stock group.
3. Inside a group, products take turns by kind, round-robin. Kind is the
   product's first room/purpose category («Для ванни», «Під двері», ...),
   or none for a plain rug. Each kind is numbered newest first
   (ROW_NUMBER), and the listing is ordered by that number. Small
   accessories (bath and door mats) count with a stride of 3, so a page of
   12 holds about 3 of them next to 9 rugs, instead of 6 and 6. Rugs are
   what the country categories and the collection are about.
4. Ties: main kinds first, then newest, then pk, so the order never
   flickers between requests and the pages never overlap.

Inside a single-kind category («Для ванни») every product has the same
kind, so the order there stays "in stock, newest first".

An explicit sort chosen by the shopper (`?sort=`, or the filter's own
`?price=` / `?title=` ordering) always wins: callers skip this then.
"""

from __future__ import annotations

from django.db.models import (
    Case,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
    Window,
)
from django.db.models.functions import Coalesce, RowNumber

#: Small accessories that should not crowd out rugs on mixed listings.
ACCESSORY_CATEGORY_SLUGS = ("dlia-vanni", "pid-dveri")
#: One accessory per this many places in the round-robin.
ACCESSORY_STRIDE = 3
#: Title marker of products still waiting for a real name.
PLACEHOLDER_TITLE = "без назви"
PLACEHOLDER_IMAGES = ("", "products/default.png")

#: GET keys that mean the shopper picked an order.
EXPLICIT_SORT_KEYS = ("sort", "price", "title")


class _WindowValue(ExpressionWrapper):
    """An expression built on a window function (ROW_NUMBER() * stride).

    Django puts any non-aggregate SELECT expression into GROUP BY. The
    manager's Sum() makes this a grouped query, and a window function in
    GROUP BY is an SQL error ("misuse of window function"). A window is
    computed after grouping, so it never belongs there.
    """

    contains_over_clause = True

    def get_group_by_cols(self, *args, **kwargs):
        return []


def has_explicit_sort(params) -> bool:
    return any((params.get(key) or "").strip() for key in EXPLICIT_SORT_KEYS)


def _room_slug_subquery():
    from project.merchant_feed import COUNTRY_CATEGORIES

    from .models import Product

    through = Product.categories.through
    return Subquery(
        through.objects.filter(product_id=OuterRef("pk"))
        .exclude(productcategory__title__in=COUNTRY_CATEGORIES)
        .order_by("productcategory_id")
        .values("productcategory__slug")[:1]
    )


def diversified(queryset):
    """`queryset` (from `Product.objects`) in the mixed default order."""
    weak = Q(title__icontains=PLACEHOLDER_TITLE) | Q(image__in=PLACEHOLDER_IMAGES)
    qs = queryset.annotate(_kind=Coalesce(_room_slug_subquery(), Value(""))).annotate(
        _stride=Case(
            When(_kind__in=ACCESSORY_CATEGORY_SLUGS, then=Value(ACCESSORY_STRIDE)),
            default=Value(1),
            output_field=IntegerField(),
        ),
        _weak=Case(When(weak, then=Value(1)), default=Value(0), output_field=IntegerField()),
    )
    turn = Window(
        expression=RowNumber(),
        partition_by=[
            F("has_attribute_with_quantity_gt_zero"),
            F("_weak"),
            F("_kind"),
        ],
        order_by=[F("created").desc(), F("pk").desc()],
    )
    qs = qs.annotate(
        _slot=_WindowValue(turn * F("_stride"), output_field=IntegerField())
    )
    return qs.order_by(
        "has_attribute_with_quantity_gt_zero",
        "_weak",
        "_slot",
        "_stride",
        "_kind",
        "-created",
        "-pk",
    )
