"""Resolve product / size from URL, slug, title."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from django.db.models import Q

from catalog.models import Product, ProductAttribute

PRODUCT_URL_RE = re.compile(
    r"(?:https?://[^\s]+)?/catalog/product/(?P<slug>[\w\-]+)/?",
    re.I,
)
SIZE_RE = re.compile(
    r"(?P<a>\d+(?:[.,]\d+)?)\s*[xх×]\s*(?P<b>\d+(?:[.,]\d+)?)",
    re.I,
)


def normalize_size(text: str) -> str:
    m = SIZE_RE.search(text or "")
    if not m:
        return (text or "").strip().casefold().replace("х", "x").replace("×", "x")
    a = m.group("a").replace(",", ".")
    b = m.group("b").replace(",", ".")
    return f"{a}x{b}"


def sizes_equal(a: str, b: str) -> bool:
    return normalize_size(a) == normalize_size(b)


def extract_slug_from_text(text: str) -> str | None:
    m = PRODUCT_URL_RE.search(text or "")
    if m:
        return m.group("slug")
    # bare slug-ish
    m2 = re.search(r"\b(kilim[\w\-]+)\b", text or "", re.I)
    if m2:
        return m2.group(1)
    return None


def extract_size_from_text(text: str) -> str | None:
    m = SIZE_RE.search(text or "")
    if not m:
        return None
    return normalize_size(m.group(0))


def find_product(query: str = "", slug: str = "", url: str = "") -> Product | None:
    slug = (slug or extract_slug_from_text(url or query) or "").strip()
    if slug:
        p = Product.admin_objects.filter(slug__iexact=slug).first()
        if p:
            return p
    q = (query or "").strip()
    # strip url from query for title search
    q = PRODUCT_URL_RE.sub(" ", q).strip()
    q = re.sub(r"\s+", " ", q)
    if not q:
        return None
    # drop size tokens for title match
    q_title = SIZE_RE.sub(" ", q)
    q_title = re.sub(
        r"\b(розмір|постав|збільш\w*|зменш\w*|додай|кількість|шт|штук)\b",
        " ",
        q_title,
        flags=re.I,
    )
    q_title = re.sub(r"[+\-]\s*\d+", " ", q_title)
    q_title = re.sub(r"\s+", " ", q_title).strip(" ,.-")
    if len(q_title) < 3:
        return None
    return (
        Product.admin_objects.filter(
            Q(title__icontains=q_title) | Q(slug__icontains=q_title)
        )
        .order_by("id")
        .first()
    )


def find_product_attr(product: Product, size_label: str | None) -> ProductAttribute | None:
    attrs = list(
        product.product_attr.select_related("size").filter(custom_attribute=False)
    )
    if not attrs:
        attrs = list(product.product_attr.select_related("size").all())
    if not attrs:
        return None
    if not size_label:
        # prefer in-stock default
        for a in attrs:
            if a.in_stock:
                return a
        return attrs[0]
    for a in attrs:
        label = str(a.size) if a.size else ""
        if sizes_equal(label, size_label):
            return a
    return None
