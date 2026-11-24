"""Sibling products of one carpet model: other shapes and other colours.

The shop lists every shape and colour of a model as its own product with its
own URL ("Килим овальний сірий Mira 24031.619 O" and "Килим прямокутний сірий
Mira 24031.619"). To Google those pages are near-duplicates, and the oval ones
were only reachable through deep catalog pagination, so 26 of them sat in
"Discovered – currently not indexed". A server-rendered block of plain links
between the siblings gives each one an internal link from a page Google
already indexes, and spells out what differs (shape, colour) in the anchor.

Colour siblings are explicit (`color_group`). Shape siblings are not modelled
at all, so they are matched by the model code in the title: the tokens that
carry a digit ("gk500", "24031.619" -> "24031619"), or, when a title has no
code, its Latin series words ("wilma"). Shape and colour words never take
part, which is exactly what makes "овальний" and "прямокутний" match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Latin or digits; dots, slashes and hyphens inside a code glue it together
# ("24031.619", "1918/19", "MR-460", "19682-91").
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[./\-][a-z0-9]+)*", re.IGNORECASE)
# Trailing shape markers some titles carry: "... 12500.90 O", "... Oval".
_SHAPE_TOKENS = {"o", "oval", "ovl"}

SHAPE_LABELS = (
    # (title stem, spec value stem, label shown to the shopper)
    ("овал", "овал", "Овальний"),
    ("прямокут", "прямокут", "Прямокутний"),
    ("кругл", "круг", "Круглий"),
    ("напівкол", "напівкол", "Напівколо"),
)


def model_key(title: str | None) -> str:
    """Model code of a product title, '' when the title carries none."""
    tokens = [t.lower() for t in _TOKEN_RE.findall(title or "")]
    tokens = [t for t in tokens if t not in _SHAPE_TOKENS]
    codes = [re.sub(r"[./\-]", "", t) for t in tokens if any(c.isdigit() for c in t)]
    if codes:
        return " ".join(codes)
    return " ".join(tokens)


_SHAPE_PHRASES = {
    "Овальний": "овальної форми",
    "Прямокутний": "прямокутної форми",
    "Круглий": "круглої форми",
    "Напівколо": "у формі напівкола",
}


def shape_label(product) -> str:
    """"Овальний" / "Прямокутний" / ... from the title, else the shape spec.

    Title first on purpose: on the live site two oval rugs (La Rosa GK500 O,
    ModernGK506 O) carry the spec "Прямокутник", while the title and photo
    say oval. The title is what the shopper reads, so it decides.
    """
    title = (product.title or "").lower()
    for title_stem, _spec_stem, label in SHAPE_LABELS:
        if title_stem in title:
            return label
    for row in product.product_specs.all():
        spec = row.specification
        if spec and row.spec_value and "форм" in (spec.title or "").lower():
            spec_value = (row.spec_value.title or "").lower()
            for _title_stem, spec_stem, label in SHAPE_LABELS:
                if spec_stem in spec_value:
                    return label
            break
    return ""


def shape_phrase(label: str) -> str:
    """"овальної форми" for the intro sentence, '' when the shape is unknown."""
    return _SHAPE_PHRASES.get(label, "")


def color_label(product) -> str:
    """Colour words from the title first (what the shopper reads and what the
    Merchant feed sends), the admin's active_color only when the title has
    none: on the live site active_color was wrong on several rugs
    (a grey ModernGK506 marked "Синій"). Always lower case, as title colours
    are, so chips read alike whichever source a sibling's colour came from
    ("Овальний, сірий" next to "Прямокутний, срібний", not "..., Срібний")."""
    from project.merchant_feed import parse_title

    colors = parse_title(getattr(product, "title", "") or "")["colors"]
    if colors:
        return "/".join(colors[:3])
    color = getattr(product, "active_color", None)
    return (color.title or "").strip().lower() if color else ""


@dataclass
class VariantLink:
    product: object
    url: str
    title: str
    shape: str
    color: str
    same_shape: bool
    price: object = None

    @property
    def label(self) -> str:
        parts = [p for p in (self.shape, self.color) if p]
        if not parts:
            return self.title
        text = ", ".join(parts)
        return text[:1].upper() + text[1:]  # colour alone: "Сірий", not "сірий"


def sibling_products(product, limit: int = 12):
    """Other visible products of the same model, colour group first.

    Uses the storefront manager, so hidden or attribute-less products are
    never linked (a link to a 404 is worse than no link).
    """
    from catalog.models import Product

    base = Product.objects.select_related("active_color").prefetch_related(
        "product_specs__specification", "product_specs__spec_value", "product_attr"
    )

    found: dict[int, object] = {}
    if product.color_group_id:
        for p in base.filter(color_group_id=product.color_group_id).exclude(
            pk=product.pk
        ):
            found[p.pk] = p

    key = model_key(product.title)
    # A bare one-word key ("wilma") is too weak to call two products the same
    # model unless it is a real code; only codes and multi-word series match.
    strong = bool(key) and (any(c.isdigit() for c in key) or " " in key)
    if strong:
        for pk, title in Product.objects.exclude(pk=product.pk).values_list(
            "pk", "title"
        ):
            if pk not in found and model_key(title) == key:
                found[pk] = None
        missing = [pk for pk, p in found.items() if p is None]
        if missing:
            for p in base.filter(pk__in=missing):
                found[p.pk] = p

    siblings = [p for p in found.values() if p is not None]
    return siblings[:limit]


def variant_links(product, limit: int = 12) -> list[VariantLink]:
    own_shape = shape_label(product)
    links = []
    for p in sibling_products(product, limit=limit):
        shape = shape_label(p)
        default = p.get_default_size_attr()
        price = None
        if default is not None and not default.custom_attribute:
            price = default.get_total_price()
        links.append(
            VariantLink(
                product=p,
                url=p.get_absolute_url(),
                title=p.title,
                shape=shape,
                color=color_label(p),
                same_shape=bool(shape) and shape == own_shape,
                price=price,
            )
        )
    # Other shapes first: those are the pages that need the link most.
    links.sort(key=lambda link: (link.same_shape, link.shape, link.color))
    return links
