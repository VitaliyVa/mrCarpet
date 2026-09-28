"""Google Merchant Center product feed (RSS 2.0 + g: namespace).

One feed item per sellable size (ProductAttribute). Sizes of one product share
`item_group_id`, so Google shows them as variants of one listing.

Facts only from the DB: brand is always mr.Carpet, no GTIN exists
(`identifier_exists=no`), id is stable `<product.pk>-<attr.pk>`.
Custom-size attributes (price per m², no fixed price) are skipped.
"""

from __future__ import annotations

import re
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils.html import strip_tags

from project.seo_jsonld import ORG_NAME, _google_product_category, _product_color
from project.seo_urls import absolute_site_url
from project.text_encoding import fix_utf8_mojibake

MAX_ADDITIONAL_IMAGES = 10
_SIZE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[xхXХ×]\s*(\d+(?:[.,]\d+)?)\s*$")


def format_size(raw: str | None) -> str:
    """'1.2х2.0' (metres, Cyrillic x) -> '120x200 см'. Unknown formats pass through."""
    value = (raw or "").strip()
    match = _SIZE_RE.match(value)
    if not match:
        return value
    width, length = (float(g.replace(",", ".")) for g in match.groups())
    if width < 10 and length < 10:  # metres
        width, length = width * 100, length * 100
    return f"{round(width)}x{round(length)} см"


def _money(value) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))} UAH"


def _text(value: str | None, limit: int) -> str:
    return fix_utf8_mojibake(strip_tags(value or "")).strip()[:limit]


def _tag(name: str, value) -> str:
    if value is None or value == "":
        return ""
    return f"<g:{name}>{escape(str(value))}</g:{name}>"


def _image_urls(product) -> list[str]:
    urls = []
    # products/default.png is the upload placeholder: Google flags it as a
    # generic image and disapproves the item, so it never becomes image_link.
    if product.image and not product.image.name.endswith("default.png"):
        urls.append(absolute_site_url(product.image.url))
    for img in product.images.all().order_by("sort_order", "pk"):
        if img.image:
            urls.append(absolute_site_url(img.image.url))
    return urls


def build_items(products) -> list[dict]:
    items: list[dict] = []
    for product in products:
        images = _image_urls(product)
        if not images:
            continue  # Google rejects items without image_link
        description = _text(
            product.meta_description or product.description or product.title, 5000
        )
        link = absolute_site_url(product.get_absolute_url())
        color = _product_color(product)
        categories = list(product.categories.all())
        product_type = categories[0].title if categories else ""
        google_category = _google_product_category(product)

        for attr in product.product_attr.select_related("size").order_by(
            "sort_order", "pk"
        ):
            if attr.custom_attribute or not attr.price:
                continue
            size = format_size(attr.size.title if attr.size else "")
            total = attr.get_total_price()
            item = {
                "id": f"{product.pk}-{attr.pk}",
                "item_group_id": str(product.pk),
                "title": _text(f"{product.title} {size}".strip(), 150),
                "description": description,
                "link": link,
                "image_link": images[0],
                "additional_image_link": images[1 : 1 + MAX_ADDITIONAL_IMAGES],
                "availability": "in_stock" if (attr.quantity or 0) > 0 else "out_of_stock",
                "price": _money(attr.price),
                "sale_price": _money(total) if attr.discount and total != attr.price else "",
                "condition": "new",
                "brand": ORG_NAME,
                "identifier_exists": "no",
                "google_product_category": google_category,
                "product_type": product_type,
                "size": size,
                "color": color or "",
            }
            items.append(item)
    return items


def render_feed(items: list[dict]) -> str:
    base = absolute_site_url("/").rstrip("/")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">',
        "<channel>",
        f"<title>{escape(ORG_NAME)}</title>",
        f"<link>{escape(base)}</link>",
        "<description>Килими mr.Carpet</description>",
    ]
    for item in items:
        parts.append("<item>")
        for key, value in item.items():
            if isinstance(value, list):
                parts.extend(_tag(key, v) for v in value)
            else:
                parts.append(_tag(key, value))
        parts.append("</item>")
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(p for p in parts if p)


def build_feed() -> str:
    from catalog.models import Product

    products = (
        Product.objects.all()
        .select_related("active_color")
        .prefetch_related("categories", "images")
    )
    return render_feed(build_items(products))
