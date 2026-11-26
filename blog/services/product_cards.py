"""Live product cards inside article bodies.

An article stores only a placeholder::

    <div class="blog-products" data-products="slug-1,slug-2"></div>

and the cards are drawn from the catalogue at render time, so price,
discount, stock and photo always match the shop. A product typed into the
article as static HTML would keep yesterday's price forever.

Unknown slugs, and products the catalogue itself hides (``Product.objects``
drops items without variations, the same rule the product page uses), are
skipped silently. A block with nothing left to show disappears.
"""

from __future__ import annotations

import re

from django.template.loader import render_to_string

from project.merchant_feed import offer_id

#: Cards per block. A fifth card wraps onto a lonely second row on desktop.
MAX_PRODUCTS = 4

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,254}$")

#: The sanitizer emits this exact form (see html_sanitize), so the pattern can
#: be strict.
PLACEHOLDER_RE = re.compile(
    r'<div class="blog-products" data-products="([^"]*)">.*?</div>', re.S
)


def parse_slugs(value: str | None) -> list[str]:
    """«a, b,,c» → ['a', 'b', 'c']: lowercase, deduplicated, valid slugs, at most four."""
    slugs: list[str] = []
    for raw in (value or "").split(","):
        slug = raw.strip().lower()
        if slug and SLUG_RE.match(slug) and slug not in slugs:
            slugs.append(slug)
        if len(slugs) == MAX_PRODUCTS:
            break
    return slugs


#: Card slots are 140-220 px wide; 480 covers the big card on 2x screens,
#: 240 the sidebar mini card and 1x phones.
CARD_IMAGE_WIDTHS = (240, 480)


def _image_urls(product) -> dict[int, str] | None:
    """{240: url, 480: url} of resized WebP copies, or None without a photo.

    ``thumbnail_url`` falls back to the original URL when it cannot resize,
    so a card never loses its picture over a thumbnail problem."""
    image = getattr(product, "image", None)
    name = getattr(image, "name", "") or ""
    if not name:
        return None
    try:
        if not image.storage.exists(name):
            return None
        original = image.url
    except Exception:  # storage hiccup must not take the article down
        return None
    from catalog.thumbnails import thumbnail_url

    urls = {}
    for width in CARD_IMAGE_WIDTHS:
        try:
            urls[width] = thumbnail_url(image, width) or original
        except Exception:
            urls[width] = original
    return urls


def _format_price(value) -> str:
    """12500 → «12 500», 1997.5 → «1 997,50». Narrow no-break space keeps the number on one line."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number.is_integer():
        text = f"{int(number):,}"
    else:
        text = f"{number:,.2f}"
    # Ukrainian style: space between thousands, comma before kopecks.
    return text.replace(",", " ").replace(".", ",")


def build_card(product) -> dict | None:
    attrs = list(product.product_attr.all())
    if not attrs:
        return None

    sized = [a for a in attrs if not a.custom_attribute and a.price]
    in_stock = any(a.in_stock for a in attrs)
    variant = ""
    ga_attr = None

    if sized:
        # Cheapest size someone can buy now; fall back to all sizes when
        # nothing is in stock so the card still says what it costs.
        pool = [a for a in sized if a.in_stock] or sized
        cheapest = min(pool, key=lambda a: a.get_total_price())
        price_value = cheapest.get_total_price()
        variant = str(cheapest.size) if getattr(cheapest, "size_id", None) else ""
        ga_attr = cheapest
        price = _format_price(price_value)
        unit = "грн"
        old_price = _format_price(cheapest.price) if cheapest.discount else ""
        discount = max((a.discount or 0) for a in pool)
        # «−10%» next to a price that is not discounted reads as a lie;
        # when only another size is on sale, say «до −10%».
        discount_upto = bool(discount) and not cheapest.discount
        from_label = len(sized) > 1
    else:
        custom = next((a for a in attrs if a.custom_attribute and a.custom_price), None)
        if custom is None:
            return None
        price_value = custom.custom_price
        price = _format_price(price_value)
        unit = "грн/м²"
        old_price = ""
        discount = 0
        discount_upto = False
        from_label = True

    try:
        ga_price = round(float(price_value), 2)
    except (TypeError, ValueError):
        ga_price = 0.0
    images = _image_urls(product)
    return {
        # GA4 item fields (same shape as project/ga4_ecommerce.py).
        "id": product.pk,
        "ga_price": f"{ga_price:.2f}",
        "ga_variant": variant,
        # Merchant feed g:id of the size the card prices (bare pk otherwise).
        "ga_item_id": offer_id(product, ga_attr),
        "title": product.title,
        "url": product.get_absolute_url(),
        # 480 px WebP for the big card, 240 px for the sidebar mini card.
        "image": images[480] if images else None,
        "image_small": images[240] if images else None,
        "price": price,
        "unit": unit,
        "from_label": from_label,
        "old_price": old_price,
        "discount": discount,
        "discount_upto": discount_upto,
        "in_stock": in_stock,
    }


def cards_for(slugs: list[str]) -> list[dict]:
    if not slugs:
        return []
    from catalog.models import Product

    found = {
        p.slug: p
        for p in Product.objects.filter(slug__in=slugs).prefetch_related(
            "product_attr", "product_attr__size"
        )
    }
    cards = []
    for slug in slugs:  # keep the author's order
        product = found.get(slug)
        card = build_card(product) if product else None
        if card:
            cards.append(card)
    return cards


def render_block(slugs: list[str]) -> str:
    cards = cards_for(slugs)
    if not cards:
        return ""
    return render_to_string("includes/blog_products.html", {"cards": cards}).strip()


def expand_product_blocks(html: str) -> str:
    """Replace every placeholder in sanitized article HTML with live cards."""
    if not html or "blog-products" not in html:
        return html
    return PLACEHOLDER_RE.sub(lambda m: render_block(parse_slugs(m.group(1))), html)


ANY_PRODUCTS_RE = re.compile(r'data-products="([^"]*)"')


def article_product_cards(html: str | None, limit: int = MAX_PRODUCTS) -> list[dict]:
    """Cards for every product an article recommends inline, deduplicated,
    in reading order, at most `limit`. Feeds the sidebar mini cards so the
    reader can reach the recommended rugs without scrolling back."""
    slugs: list[str] = []
    for m in ANY_PRODUCTS_RE.finditer(html or ""):
        for slug in parse_slugs(m.group(1)):
            if slug not in slugs:
                slugs.append(slug)
    candidates = cards_for(slugs[: limit * 2])
    return candidates[:limit]

