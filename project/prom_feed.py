"""YML (Yandex Market Language) product feeds for Prom.ua and Rozetka.

Two renderers share the product data:

- `build_feed()` is the generic Prom.ua feed. Not wired to any URL: Prom
  needs a paid, identity-verified seller account first. Run it by hand and
  upload the XML.
- `build_rozetka_feed()` is the Rozetka Marketplace feed, served at
  /feeds/rozetka.xml (requirements: sellerhelp.rozetka.com.ua/p185-pricelist-requirements.html).

One offer per sellable size (ProductAttribute), grouped by `group_id` so the
marketplace shows sizes as variants of one card.

Rozetka specifics:
- offer id is `<product.pk>x<attr.pk>` (Rozetka allows only A-Za-z0-9, so the
  dash of the Google id `<product.pk>-<attr.pk>` is replaced by `x`); stable
  as long as the rows exist. category id is ProductCategory.pk;
- price = site price (after discount) * ROZETKA_PRICE_MARKUP (settings,
  default 1.25: Rozetka commission ~20%, 1/0.8), rounded to whole UAH;
- `vendor` comes from a «Бренд» / «Торгова марка» spec, else the fallback
  `mr.Carpet` (see `rozetka_vendor`);
- `name` and `name_ua` are both Ukrainian (there is no Russian site) and are
  made unique per offer;
- custom-size (cut to length) and price-less sizes are skipped.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from django.utils.html import strip_tags

from project.merchant_feed import (
    COUNTRY_CATEGORIES,
    _image_urls as _merchant_image_urls,
    feed_products,
    feed_title,
    format_size,
    product_color,
    product_description,
    product_shape,
    product_specs,
    variant_link,
)
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
        description = product_description(product, 3000)
        specs = product_specs(product)
        color = product_color(product, specs)
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
                    ("Колір", color),
                    *((n, v) for n, v in specs if n.lower() not in ("розмір", "колір")),
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
    from catalog.models import ProductCategory

    products = feed_products()
    categories = build_categories(ProductCategory.objects.all())
    offers = build_offers(products)
    return render_feed(categories, offers)


# --- Rozetka Marketplace ----------------------------------------------------

ROZETKA_SHOP_NAME = "Mr Carpet"
ROZETKA_COMPANY = "ФОП Стецюк Микола Олексійович"
ROZETKA_FALLBACK_VENDOR = ORG_NAME  # "mr.Carpet"
ROZETKA_FALLBACK_CATEGORY_ID = 1000000  # products without any category
ROZETKA_FALLBACK_CATEGORY_NAME = "Килими"
ROZETKA_MAX_NAME = 255
ROZETKA_MAX_PARAM = 500
ROZETKA_MAX_PICTURES = 15
ROZETKA_MAX_PICTURE_URL = 1999
ROZETKA_MAX_DESCRIPTION = 3000
ROZETKA_DEFAULT_MARKUP = "1.25"

_VENDOR_SPEC_KEYS = ("бренд", "торгова марка", "торговельна марка", "торгова марк")
_COUNTRY_BY_CATEGORY = {"Турецькі": "Туреччина", "Українські": "Україна"}
_STANDARD_PARAMS = {"розмір", "колір", "форма", "країна-виробник товару"}
_PICTURE_SAFE = ":/%?&=+~-._,;@!$'()*"


def rozetka_markup() -> Decimal:
    raw = getattr(settings, "ROZETKA_PRICE_MARKUP", ROZETKA_DEFAULT_MARKUP)
    try:
        value = Decimal(str(raw))
    except Exception:
        return Decimal(ROZETKA_DEFAULT_MARKUP)
    return value if value > 0 else Decimal(ROZETKA_DEFAULT_MARKUP)


def rozetka_price(site_price, markup: Decimal | None = None) -> int:
    """Site price (after discount) * markup, whole UAH, halves round up."""
    markup = rozetka_markup() if markup is None else markup
    scaled = Decimal(str(site_price)) * markup
    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rozetka_offer_id(product, attr) -> str:
    """`<product.pk>x<attr.pk>`: the Google id without the dash (A-Za-z0-9 only)."""
    return f"{product.pk}x{attr.pk}"


# Collections that other Rozetka sellers list under the brand Karat (Karat
# Carpet, Ukraine). Checked on rozetka.com.ua 25.11.2026: Mira, Flex, Oksi,
# Fashion, Fantasy, Lana all appear as «Килим Karat <collection>».
KARAT_COLLECTIONS = ("mira", "flex", "oksi", "fashion", "fantasy", "lana")


def rozetka_vendor(specs: list[tuple[str, str]], title: str = "") -> tuple[str, bool]:
    """(vendor, is_fallback): brand from a «Бренд» / «Торгова марка» spec,
    else Karat for its known collections, else the shop's own label."""
    for name, value in specs:
        lower = name.lower()
        if value and any(k in lower for k in _VENDOR_SPEC_KEYS):
            return value[:ROZETKA_MAX_PARAM], False
    words = set((title or "").lower().replace("/", " ").split())
    if words & set(KARAT_COLLECTIONS):
        return "Karat", False
    return ROZETKA_FALLBACK_VENDOR, True


def rozetka_picture_url(url: str) -> str:
    """Spaces / Cyrillic percent-encoded; existing %XX escapes are kept."""
    return quote(url, safe=_PICTURE_SAFE)


def rozetka_pictures(product) -> list[str]:
    urls: list[str] = []
    for url in _merchant_image_urls(product):
        encoded = rozetka_picture_url(url)
        if (
            encoded.startswith("https://")
            and len(encoded) <= ROZETKA_MAX_PICTURE_URL
            and encoded not in urls
        ):
            urls.append(encoded)
    return urls[:ROZETKA_MAX_PICTURES]


def rozetka_category_id(categories) -> int:
    """First non-country category (the room), else the first; pk order."""
    ordered = sorted(categories, key=lambda c: c.pk)
    for c in ordered:
        if c.title not in COUNTRY_CATEGORIES:
            return c.pk
    return ordered[0].pk if ordered else ROZETKA_FALLBACK_CATEGORY_ID


def _rozetka_country(specs, categories) -> str:
    for name, value in specs:
        if "країна" in name.lower() and value:
            return value
    for c in sorted(categories, key=lambda c: c.pk):
        if c.title in _COUNTRY_BY_CATEGORY:
            return _COUNTRY_BY_CATEGORY[c.title]
    return ""


def _rozetka_params(specs, size, color, shape, country) -> list[tuple[str, str]]:
    params = [
        ("Розмір", size),
        ("Колір", color),
        ("Форма", shape),
        ("Країна-виробник товару", country),
    ]
    params += [(n, v) for n, v in specs if n.lower() not in _STANDARD_PARAMS]
    return [
        (name[:ROZETKA_MAX_PARAM], value[:ROZETKA_MAX_PARAM])
        for name, value in params
        if name and value
    ]


def _unique_name(name: str, product, seen: set[str]) -> str:
    base = name
    n = 1
    while name in seen:
        suffix = f" (арт. {product.pk})" if n == 1 else f" (арт. {product.pk}-{n})"
        name = base[: ROZETKA_MAX_NAME - len(suffix)].rstrip() + suffix
        n += 1
    seen.add(name)
    return name


def build_rozetka_categories(categories) -> list[dict]:
    return [
        {"id": c.pk, "name": (c.title or "").strip()[:ROZETKA_MAX_NAME]}
        for c in categories
        if (c.title or "").strip()
    ]


def build_rozetka_offers(products) -> list[dict]:
    markup = rozetka_markup()
    offers: list[dict] = []
    seen_names: set[str] = set()
    # pk order keeps the name de-duplication suffixes stable between fetches
    for product in sorted(products, key=lambda p: p.pk):
        pictures = rozetka_pictures(product)
        if not pictures:
            continue
        description = product_description(product, ROZETKA_MAX_DESCRIPTION)
        specs = product_specs(product)
        color = product_color(product, specs)
        vendor, vendor_fallback = rozetka_vendor(specs, product.title)
        categories = list(product.categories.all())
        category_id = rozetka_category_id(categories)
        country = _rozetka_country(specs, categories)

        attrs = sorted(product.product_attr.all(), key=lambda a: (a.sort_order, a.pk))
        for attr in attrs:
            if attr.custom_attribute or not attr.price:
                continue
            size = format_size(attr.size.title if attr.size else "")
            total = attr.get_total_price()
            site_price = total if total else attr.price
            name = _unique_name(
                feed_title(product, size, specs, color)[:ROZETKA_MAX_NAME],
                product,
                seen_names,
            )
            quantity = max(int(attr.quantity or 0), 0)
            offers.append({
                "id": rozetka_offer_id(product, attr),
                "group_id": str(product.pk),
                "available": "true" if quantity > 0 else "false",
                "stock_quantity": quantity,
                "url": variant_link(product, attr),
                "price": rozetka_price(site_price, markup),
                "currencyId": "UAH",
                "categoryId": category_id,
                "pictures": pictures,
                "vendor": vendor,
                "vendor_fallback": vendor_fallback,
                "article": rozetka_offer_id(product, attr),
                "name": name,
                "name_ua": name,
                "description": description,
                "params": _rozetka_params(
                    specs, size, color, product_shape(product, specs, size), country
                ),
            })
    return offers


def _cdata(text: str) -> str:
    """Plain text -> CDATA with <p> paragraphs (split on blank lines)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    markup = "".join(
        "<p>" + escape(p).replace("\n", "<br>") + "</p>" for p in paragraphs
    )
    return "<![CDATA[" + markup.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def render_rozetka_feed(categories: list[dict], offers: list[dict]) -> str:
    base = absolute_site_url("/")
    now = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<yml_catalog date="{now}">',
        "<shop>",
        f"<name>{escape(ROZETKA_SHOP_NAME)}</name>",
        f"<company>{escape(ROZETKA_COMPANY)}</company>",
        f"<url>{escape(base)}</url>",
        '<currencies><currency id="UAH" rate="1"/></currencies>',
        "<categories>",
    ]
    all_categories = list(categories)
    known = {c["id"] for c in all_categories}
    if (
        any(o["categoryId"] == ROZETKA_FALLBACK_CATEGORY_ID for o in offers)
        and ROZETKA_FALLBACK_CATEGORY_ID not in known
    ):
        all_categories.append(
            {"id": ROZETKA_FALLBACK_CATEGORY_ID, "name": ROZETKA_FALLBACK_CATEGORY_NAME}
        )
    for c in all_categories:
        parts.append(f'<category id="{c["id"]}">{escape(c["name"])}</category>')
    parts += ["</categories>", "<offers>"]
    for o in offers:
        parts.append(
            f'<offer id="{escape(o["id"])}" available="{o["available"]}"'
            f' group_id="{escape(o["group_id"])}">'
        )
        parts.append(f'<url>{escape(o["url"])}</url>')
        parts.append(f'<price>{o["price"]}</price>')
        parts.append(f'<currencyId>{o["currencyId"]}</currencyId>')
        parts.append(f'<categoryId>{o["categoryId"]}</categoryId>')
        for pic in o["pictures"]:
            parts.append(f"<picture>{escape(pic)}</picture>")
        parts.append(f'<vendor>{escape(o["vendor"])}</vendor>')
        parts.append(f'<article>{escape(o["article"])}</article>')
        parts.append(f'<stock_quantity>{o["stock_quantity"]}</stock_quantity>')
        parts.append(f'<name>{escape(o["name"])}</name>')
        parts.append(f'<name_ua>{escape(o["name_ua"])}</name_ua>')
        parts.append(f'<description>{_cdata(o["description"])}</description>')
        parts.append(f'<description_ua>{_cdata(o["description"])}</description_ua>')
        for pname, pvalue in o["params"]:
            attr_name = escape(pname, {'"': "&quot;"})
            parts.append(f'<param name="{attr_name}">{escape(pvalue)}</param>')
        parts.append("</offer>")
    parts += ["</offers>", "</shop>", "</yml_catalog>", ""]
    return "\n".join(parts)


def build_rozetka_feed() -> str:
    from catalog.models import ProductCategory

    categories = build_rozetka_categories(ProductCategory.objects.all().order_by("pk"))
    offers = build_rozetka_offers(feed_products())
    return render_rozetka_feed(categories, offers)
