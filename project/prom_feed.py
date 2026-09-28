"""YML (Yandex Market Language) product feed — shared format for Prom.ua and
Rozetka Marketplace (both accept the same YML spec for catalog import).

Not wired to any URL yet: Prom/Rozetka require a paid, identity-verified
seller account before a feed can be imported (see docs/session-2026-09-28-seo-marketplaces.md).
Once that account exists, point its "feed URL" field at
/feeds/prom.yml (add the urls.py line — deliberately left out so this file
can't be crawled/imported before a real account is ready) or run
`build_feed()` and upload the XML by hand.

One offer per sellable size (ProductAttribute), grouped by `group_id` so
Prom/Rozetka show sizes as variants of one card. Category tree is generated
from ProductCategory so every offer's categoryId resolves.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from django.utils import timezone
from django.utils.html import strip_tags

from project.merchant_feed import format_size
from project.seo_jsonld import ORG_NAME
from project.seo_urls import absolute_site_url
from project.text_encoding import fix_utf8_mojibake

# Prom/Rozetka's own category picker remaps these on first import anyway, but
# a starting categoryId is required by the YML schema.
CATEGORY_ROOT_ID = 1
CATEGORY_ROOT_NAME = "Килими"


def _text(value: str | None, limit: int) -> str:
    return fix_utf8_mojibake(strip_tags(value or "")).strip()[:limit]


def _image_urls(product) -> list[str]:
    urls = []
    if product.image and not product.image.name.endswith("default.png"):
        urls.append(absolute_site_url(product.image.url))
    for img in product.images.all().order_by("sort_order", "pk"):
        if img.image:
            urls.append(absolute_site_url(img.image.url))
    return urls[:10]  # Prom limits 10 images per offer


def build_categories(categories) -> list[dict]:
    return [{"id": CATEGORY_ROOT_ID, "name": CATEGORY_ROOT_NAME, "parentId": None}] + [
        {"id": CATEGORY_ROOT_ID + c.pk, "name": c.title, "parentId": CATEGORY_ROOT_ID}
        for c in categories
    ]


def build_offers(products) -> list[dict]:
    offers: list[dict] = []
    for product in products:
        images = _image_urls(product)
        if not images:
            continue
        description = _text(
            product.meta_description or product.description or product.title, 3000
        )
        link = absolute_site_url(product.get_absolute_url())
        categories = list(product.categories.all())
        category_id = CATEGORY_ROOT_ID + categories[0].pk if categories else CATEGORY_ROOT_ID

        for attr in product.product_attr.select_related("size").order_by(
            "sort_order", "pk"
        ):
            if attr.custom_attribute or not attr.price:
                continue
            size = format_size(attr.size.title if attr.size else "")
            total = attr.get_total_price()
            offers.append({
                "id": f"{product.pk}-{attr.pk}",
                "group_id": str(product.pk),
                "available": "true" if (attr.quantity or 0) > 0 else "false",
                "categoryId": category_id,
                "price": total if total else attr.price,
                "currencyId": "UAH",
                "name": _text(f"{product.title} {size}".strip(), 250),
                "vendor": ORG_NAME,
                "description": description,
                "url": link,
                "pictures": images,
                "params": [p for p in [
                    ("Розмір", size),
                    ("Колір", (product.active_color.title if product.active_color else "")),
                ] if p[1]],
            })
    return offers


def render_feed(categories: list[dict], offers: list[dict]) -> str:
    base = absolute_site_url("/").rstrip("/")
    now = timezone.now().strftime("%Y-%m-%d %H:%M")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<yml_catalog date="{now}">',
        "<shop>",
        f"<name>{escape(ORG_NAME)}</name>",
        f"<company>{escape(ORG_NAME)}</company>",
        f"<url>{escape(base)}</url>",
        "<currencies><currency id=\"UAH\" rate=\"1\"/></currencies>",
        "<categories>",
    ]
    for c in categories:
        parent = f' parentId="{c["parentId"]}"' if c["parentId"] else ""
        parts.append(f'<category id="{c["id"]}"{parent}>{escape(c["name"])}</category>')
    parts.append("</categories>")
    parts.append("<offers>")
    for o in offers:
        parts.append(
            f'<offer id="{escape(o["id"])}" available="{o["available"]}" group_id="{escape(o["group_id"])}">'
        )
        parts.append(f'<url>{escape(o["url"])}</url>')
        parts.append(f'<price>{o["price"]}</price>')
        parts.append(f'<currencyId>{o["currencyId"]}</currencyId>')
        parts.append(f'<categoryId>{o["categoryId"]}</categoryId>')
        for pic in o["pictures"]:
            parts.append(f"<picture>{escape(pic)}</picture>")
        parts.append(f'<vendor>{escape(o["vendor"])}</vendor>')
        parts.append(f'<name>{escape(o["name"])}</name>')
        parts.append(f'<description>{escape(o["description"])}</description>')
        for pname, pvalue in o["params"]:
            parts.append(f'<param name="{escape(pname)}">{escape(pvalue)}</param>')
        parts.append("</offer>")
    parts.append("</offers>")
    parts += ["</shop>", "</yml_catalog>", ""]
    return "\n".join(parts)


def build_feed() -> str:
    from catalog.models import Product, ProductCategory

    products = (
        Product.objects.all()
        .select_related("active_color")
        .prefetch_related("categories", "images")
    )
    categories = build_categories(ProductCategory.objects.all())
    offers = build_offers(products)
    return render_feed(categories, offers)
