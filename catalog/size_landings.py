"""
Indexable landing pages for popular rug sizes: /catalog/rozmir/160x230/.

A buyer types "килим 160х230", but the only listing for a size used to be
the facet `?size=<Size.pk>`, which is `noindex, follow` and canonicalises to
the whole collection, so search had nothing to rank.

Size rows are free text in metres ("1.6х2.3", Cyrillic or Latin x) and the
same size can exist twice ("1.2x2.0" and "1.2х2.0"). A landing is therefore
keyed by the normalised size (project.merchant_feed.format_size, the same
string the Merchant feed and ads use), not by a Size row: one page per real
size, every matching Size row merged into it, width and length in a fixed
order so 400x200 and 200x400 never become two pages.

A page exists only while at least MIN_PRODUCTS different products are in
stock in that size; below that it is a 404 and leaves the sitemap, so the
site never offers Google a thin page or one that shows nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db.models import ExpressionWrapper, F, FloatField, Min, Q
from django.db.models.functions import Coalesce
from django.urls import reverse

from project.merchant_feed import format_size, size_dimensions

#: Fewer different in-stock products than this and the size has no page.
MIN_PRODUCTS = 6
#: How many chips the «Популярні розміри» row shows at most.
CHIPS_LIMIT = 10

# Lenient on input (a hand-typed Cyrillic х, upper case, spaces), strict on
# output: the canonical slug is always "<small>x<large>" in Latin x.
_SLUG_RE = re.compile(r"^\s*(\d{2,3})\s*[xхXХ×]\s*(\d{2,3})\s*$")

_MATERIAL_KEYS = ("склад", "матеріал")
_COUNTRY_KEYS = ("виробник", "країна")


def dims_slug(width: int, length: int) -> str:
    small, large = sorted((int(width), int(length)))
    return f"{small}x{large}"


def size_title_slug(title: str | None) -> str | None:
    """Size.title ("1.6х2.3", "160x230 см") -> "160x230"; None for anything
    that is not a rectangle (round "∅ 67 см", "на відріз", "M")."""
    formatted = format_size(title)
    if not formatted.endswith(" см") or formatted.startswith(("∅", "Ø", "ø")):
        return None
    dims = size_dimensions(formatted)
    if not dims or not all(dims):
        return None
    return dims_slug(*dims)


def parse_slug(value: str | None) -> str | None:
    """URL part -> canonical slug, or None when it is not a size at all."""
    match = _SLUG_RE.match(value or "")
    if not match:
        return None
    return dims_slug(int(match.group(1)), int(match.group(2)))


def _buyable_attrs():
    """Fixed sizes that can be bought right now."""
    from catalog.models import ProductAttribute

    return ProductAttribute.objects.filter(
        custom_attribute=False,
        quantity__gt=0,
        price__gt=0,
        size__isnull=False,
        product__isnull=False,
    )


def _size_ids_by_slug() -> dict[str, list[int]]:
    from catalog.models import Size

    out: dict[str, list[int]] = {}
    for pk, title in Size.objects.values_list("pk", "title"):
        slug = size_title_slug(title)
        if slug:
            out.setdefault(slug, []).append(pk)
    return out


def _products_by_slug() -> dict[str, set[int]]:
    slug_of = {
        pk: slug for slug, ids in _size_ids_by_slug().items() for pk in ids
    }
    out: dict[str, set[int]] = {}
    for size_id, product_id in _buyable_attrs().values_list("size_id", "product_id"):
        slug = slug_of.get(size_id)
        if slug:
            out.setdefault(slug, set()).add(product_id)
    return out


def landing_url(slug: str) -> str:
    return reverse("size_landing", kwargs={"size": slug})


def size_label(slug: str) -> str:
    return f"{slug} см"


@dataclass
class SizeChip:
    slug: str
    count: int

    @property
    def label(self) -> str:
        return size_label(self.slug)

    @property
    def url(self) -> str:
        return landing_url(self.slug)

    @property
    def dims(self) -> tuple[int, int]:
        a, b = self.slug.split("x")
        return int(a), int(b)


def landing_slugs() -> list[SizeChip]:
    """Every size that has a page now, largest range first."""
    chips = [
        SizeChip(slug, len(ids))
        for slug, ids in _products_by_slug().items()
        if len(ids) >= MIN_PRODUCTS
    ]
    chips.sort(key=lambda c: (-c.count, c.dims))
    return chips


def popular_sizes(products=None, limit: int = CHIPS_LIMIT, exclude: str = "") -> list[SizeChip]:
    """Chips for «Популярні розміри»: sizes with a page, the most stocked
    first when picking, shown from small to large.

    With `products` (a category's listing) only sizes that listing really
    has in stock are offered, so a chip never leads away to rugs that have
    nothing to do with the category. Never raises: it is decoration on
    pages that must keep working."""
    try:
        by_slug = _products_by_slug()
        allowed = None
        if products is not None:
            allowed = set(products.order_by().values_list("pk", flat=True))
        chips = []
        for slug, ids in by_slug.items():
            if len(ids) < MIN_PRODUCTS or slug == exclude:
                continue
            if allowed is not None and not (ids & allowed):
                continue
            chips.append(SizeChip(slug, len(ids)))
        chips.sort(key=lambda c: (-c.count, c.dims))
        chips = chips[:limit]
        chips.sort(key=lambda c: c.dims)
        return chips
    except Exception:  # pragma: no cover - defensive
        import logging

        logging.getLogger(__name__).exception("popular sizes failed")
        return []


@dataclass
class SizeLanding:
    slug: str
    size_ids: list[int]
    product_ids: set[int]
    price_from: int | None = None
    materials: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.product_ids)

    @property
    def label(self) -> str:
        return size_label(self.slug)

    @property
    def path(self) -> str:
        return landing_url(self.slug)

    @property
    def dims(self) -> tuple[int, int]:
        a, b = self.slug.split("x")
        return int(a), int(b)

    def attrs(self):
        """Buyable attributes of this size (any of the merged Size rows)."""
        return _buyable_attrs().filter(size_id__in=self.size_ids)


def _final_price_low(attrs) -> int | None:
    low = attrs.annotate(
        final_price=ExpressionWrapper(
            F("price") * (1 - Coalesce(F("discount"), 0) / 100.0),
            output_field=FloatField(),
        )
    ).aggregate(low=Min("final_price"))["low"]
    if not low:
        return None
    # Floor, like the collection description: "від 861" for 860.60 is untrue.
    return int(round(low, 2))


def _spec_values(product_ids, keys, limit: int = 3) -> list[str]:
    """Most common values of a spec among the products, as written in the
    admin (same source as the product page and the feed)."""
    from django.db.models import Count

    from catalog.models import ProductSpecification, Specification

    # Matched in Python: SQLite LIKE ignores case for ASCII only, so
    # icontains="склад" would miss "Склад килима".
    spec_ids = [
        pk
        for pk, title in Specification.objects.values_list("pk", "title")
        if any(key in (title or "").lower() for key in keys)
    ]
    if not spec_ids:
        return []
    rows = (
        ProductSpecification.objects.filter(
            specification_id__in=spec_ids, product_id__in=product_ids
        )
        .exclude(spec_value__title__isnull=True)
        .exclude(spec_value__title="")
        .values("spec_value__title")
        .annotate(n=Count("product", distinct=True))
        .order_by("-n", "spec_value__title")
    )
    seen, out = set(), []
    for row in rows:
        value = " ".join((row["spec_value__title"] or "").split())
        if value and value.lower() not in seen:
            seen.add(value.lower())
            out.append(value)
        if len(out) >= limit:
            break
    return out


def get_landing(slug: str) -> SizeLanding | None:
    """The landing for a canonical slug, or None when it must not exist."""
    size_ids = _size_ids_by_slug().get(slug) or []
    if not size_ids:
        return None
    attrs = _buyable_attrs().filter(size_id__in=size_ids)
    product_ids = set(attrs.values_list("product_id", flat=True))
    if len(product_ids) < MIN_PRODUCTS:
        return None
    return SizeLanding(
        slug=slug,
        size_ids=size_ids,
        product_ids=product_ids,
        price_from=_final_price_low(attrs),
        materials=_spec_values(product_ids, _MATERIAL_KEYS),
        countries=_spec_values(product_ids, _COUNTRY_KEYS),
    )


# --- texts -------------------------------------------------------------------
# Simple, warm, short sentences; no dashes. Every fact comes from the data.


def _lower_word(value: str) -> str:
    """"Поліпропілен" -> "поліпропілен", but "BCF" stays as is."""
    if len(value) > 1 and value[1].islower():
        return value[0].lower() + value[1:]
    return value


def _join(values: list[str]) -> str:
    if len(values) <= 1:
        return "".join(values)
    return ", ".join(values[:-1]) + " і " + values[-1]


def _models_word(n: int) -> str:
    from catalog.templatetags.catalog_filters import plural_uk_form

    return plural_uk_form(n, "модель,моделі,моделей")


def _free_shipping_threshold() -> int | None:
    try:
        from project.free_shipping import get_shop_settings

        settings = get_shop_settings()
    except Exception:  # pragma: no cover - defensive
        return None
    threshold = int(settings.free_shipping_threshold or 0)
    if settings.free_shipping_enabled and threshold > 0:
        return threshold
    return None


def landing_h1(landing: SizeLanding) -> str:
    return f"Килими {landing.label}"


def landing_meta_title(landing: SizeLanding) -> str:
    title = f"Килими {landing.label}: купити в Україні"
    if landing.price_from:
        title += f", ціни від {landing.price_from} грн"
    return title


def landing_meta_description(landing: SizeLanding) -> str:
    text = (
        f"Килими {landing.label} в наявності: {landing.count} "
        f"{_models_word(landing.count)}"
    )
    if landing.price_from:
        text += f", ціни від {landing.price_from} грн"
    text += "."
    if landing.materials:
        materials = _join([_lower_word(m) for m in landing.materials])
        text += f" {materials[:1].upper()}{materials[1:]}."
    threshold = _free_shipping_threshold()
    if threshold:
        text += f" Доставка по Україні, безкоштовно від {threshold} грн."
    else:
        text += " Доставка по Україні."
    return text


def landing_intro(landing: SizeLanding) -> str:
    width, length = landing.dims
    parts = [
        f"Тут зібрані всі килими розміром {landing.label}, які зараз є в наявності.",
        f"Ширина {width} см, довжина {length} см.",
        f"Зараз це {landing.count} {_models_word(landing.count)}"
        + (f", ціни від {landing.price_from} грн." if landing.price_from else "."),
    ]
    if landing.materials:
        word = "Матеріал" if len(landing.materials) == 1 else "Матеріали"
        parts.append(f"{word}: {_join([_lower_word(m) for m in landing.materials])}.")
    if landing.countries:
        parts.append(f"Виробництво: {_join(landing.countries)}.")
    threshold = _free_shipping_threshold()
    if threshold:
        parts.append(f"Доставка по Україні безкоштовна від {threshold} грн.")
    return " ".join(parts)


def landing_guides(landing: SizeLanding, limit: int = 3):
    """«Корисні статті»: articles about sizes first, then the newest."""
    from blog.models import Article
    from project.seo_content import get_seo_guides

    fields = ("id", "title", "slug", "description", "image", "meta_description")
    order = ("-published_at", "-created", "-pk")
    matched = list(
        Article.objects.public()
        .filter(Q(slug__icontains="rozmir") | Q(description__contains=landing.path))
        .distinct()
        .order_by(*order)
        .only(*fields)[:limit]
    )
    if len(matched) >= limit:
        return matched
    seen = {a.pk for a in matched}
    rest = [a for a in get_seo_guides(limit=limit + len(matched)) if a.pk not in seen]
    return matched + rest[: limit - len(matched)]
