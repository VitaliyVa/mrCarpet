"""Discounts and sales: one place for "what is on sale right now".

A discount lives on a size (ProductAttribute.discount, percent). ProductSale
only adds an end date (the countdown on the home page) and a product list.
`Product.has_discount` is a denormalised flag that admins can also tick by
hand, so nothing here trusts it: a product is "on sale" when one of its
fixed sizes is in stock and really costs less than its list price.
"""

from __future__ import annotations

from numbers import Number

from django.core.cache import cache
from django.db.models import Exists, OuterRef
from django.utils import timezone

PROMO_CACHE_KEY = "catalog:has_promo:v1"
#: The header asks on every page; a stale answer lasts at most this long in
#: other worker processes (the process that saved the change clears it).
PROMO_CACHE_SECONDS = 300


def discounted_attrs():
    """Fixed sizes that are in stock and sold below their list price."""
    from .models import ProductAttribute

    return ProductAttribute.objects.filter(
        custom_attribute=False,
        price__gt=0,
        quantity__gt=0,
        discount__gt=0,
        discount__lt=100,
    )


def discounted_in_stock_products():
    """Products with at least one discounted size in stock (manager order)."""
    from .models import Product

    return Product.objects.filter(
        Exists(discounted_attrs().filter(product_id=OuterRef("pk")))
    )


def has_promo() -> bool:
    """Is there anything to show on /catalog/stock/? Cached, cheap per page."""
    try:
        return bool(
            cache.get_or_set(
                PROMO_CACHE_KEY,
                lambda: discounted_in_stock_products().exists(),
                PROMO_CACHE_SECONDS,
            )
        )
    except Exception:  # pragma: no cover - a cache outage must not 500 pages
        return False


def clear_promo_cache(*_args, **_kwargs) -> None:
    try:
        cache.delete(PROMO_CACHE_KEY)
    except Exception:  # pragma: no cover
        pass


def is_real_discount(attr) -> bool:
    """A size whose price after the discount is really lower (strike-through)."""
    if attr is None or getattr(attr, "custom_attribute", False):
        return False
    discount, price = getattr(attr, "discount", None), getattr(attr, "price", None)
    if not isinstance(discount, Number) or not isinstance(price, Number):
        return False
    if discount <= 0 or price <= 0:
        return False
    total = attr.get_total_price()
    return isinstance(total, Number) and total < price


def active_sale_windows(product_ids=None) -> dict[int, tuple]:
    """{product_id: (start, end)} of the soonest ending running ProductSale.

    Only sales whose end is still ahead. A finished sale is ignored: its
    discount stays on the size until an admin removes it, so pretending the
    price ends on a date in the past would contradict the page.
    """
    from .models import ProductSale

    now = timezone.now()
    through = ProductSale.products.through
    rows = through.objects.filter(productsale__date_end__gt=now)
    if product_ids is not None:
        rows = rows.filter(product_id__in=list(product_ids))
    out: dict[int, tuple] = {}
    for product_id, created, date_end in rows.values_list(
        "product_id", "productsale__created", "productsale__date_end"
    ).order_by("productsale__date_end", "productsale_id"):
        if product_id in out:
            continue
        start = created if created and created < date_end else now
        out[product_id] = (start, date_end)
    return out


def sale_end_for(product):
    """End (datetime) of the running sale this product is in, else None."""
    window = active_sale_windows([product.pk]).get(product.pk)
    return window[1] if window else None
