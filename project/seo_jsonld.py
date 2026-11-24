"""Server-rendered JSON-LD builders (SEO Phase 4 + 7 Merchant / variants)."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.html import strip_tags

from project.seo_urls import absolute_site_url, canonical_url
from project.text_encoding import fix_utf8_mojibake

ORG_NAME = "mr.Carpet"
ORG_EMAIL = "mr.carpet.shop@gmail.com"
ORG_PHONE = "+380963988875"
ORG_STREET = "вул. Незалежності 5а"
ORG_LOCALITY = "Ланівці"
ORG_REGION = "Тернопільська область"
ORG_COUNTRY = "UA"

# Consumer return window (matches /refund/ copy: 14 days)
MERCHANT_RETURN_DAYS = 14
# Rolling price validity for Merchant listings (non-sale catalog price)
PRICE_VALID_DAYS = 90


def absolute_uri(request, path_or_url: str | None) -> str | None:
    if not path_or_url:
        return None
    value = str(path_or_url)
    if value.startswith("http://") or value.startswith("https://"):
        return value
    # Always the canonical host: www.mrcarpet24.com used to leak into JSON-LD
    # and Google then picked www as canonical for a third of the catalog.
    return absolute_site_url(value)


def dumps_jsonld(data: dict[str, Any] | list[Any]) -> str:
    """Serialize for <script type=application/ld+json>; escape </ to be safe in HTML."""
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("<", "\\u003c")


def merchant_return_policy(request) -> dict[str, Any]:
    """Shared MerchantReturnPolicy (Organization + Offer)."""
    return {
        "@type": "MerchantReturnPolicy",
        "@id": absolute_uri(request, "/refund/#merchant-return-policy"),
        "applicableCountry": ORG_COUNTRY,
        "returnPolicyCountry": ORG_COUNTRY,
        "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
        "merchantReturnDays": MERCHANT_RETURN_DAYS,
        "returnMethod": "https://schema.org/ReturnByMail",
        "returnFees": "https://schema.org/ReturnFeesCustomerResponsibility",
        "merchantReturnLink": absolute_uri(request, "/refund/"),
    }


def offer_shipping_details(price=None) -> dict[str, Any] | None:
    """OfferShippingDetails matching checkout: free from the threshold, else
    the carrier "from" price shown at checkout (Nova Poshta, paid by buyer).

    Used to claim free shipping on every offer, including 300 грн doormats.
    Merchant Center compares this with its own shipping settings and the
    checkout, so a blanket "0" is a mismatch that gets items disapproved.
    """
    rate = 0
    try:
        from project.free_shipping import get_shop_settings

        settings = get_shop_settings()
        threshold = int(settings.free_shipping_threshold or 0)
        free = bool(settings.free_shipping_enabled) and (
            price is None or (threshold > 0 and float(price) >= threshold)
        )
        if not free:
            rate = int(settings.delivery_from_price or 0)
            if not rate:
                return None
    except Exception:
        pass

    return {
        "@type": "OfferShippingDetails",
        "shippingRate": {
            "@type": "MonetaryAmount",
            "value": str(rate),
            "currency": "UAH",
        },
        "shippingDestination": {
            "@type": "DefinedRegion",
            "addressCountry": ORG_COUNTRY,
        },
        "deliveryTime": {
            "@type": "ShippingDeliveryTime",
            "handlingTime": {
                "@type": "QuantitativeValue",
                "minValue": 0,
                "maxValue": 2,
                "unitCode": "DAY",
            },
            "transitTime": {
                "@type": "QuantitativeValue",
                "minValue": 1,
                "maxValue": 5,
                "unitCode": "DAY",
            },
        },
    }


ORG_SAME_AS = (
    "https://www.facebook.com/mrcarpet24/",
    "https://www.instagram.com/mr.carpet.shop/",
    "https://www.tiktok.com/@mrcarpet24",
    "https://t.me/mrcarpet24",
)


def organization_graph(request) -> dict[str, Any]:
    logo = absolute_uri(request, "/static/utils/assets/brand/mr-carpet-logo.png")
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": ORG_NAME,
        "url": absolute_uri(request, "/"),
        "logo": logo,
        "email": ORG_EMAIL,
        "telephone": ORG_PHONE,
        "sameAs": list(ORG_SAME_AS),
        "address": {
            "@type": "PostalAddress",
            "streetAddress": ORG_STREET,
            "addressLocality": ORG_LOCALITY,
            "addressRegion": ORG_REGION,
            "addressCountry": ORG_COUNTRY,
        },
        "hasMerchantReturnPolicy": merchant_return_policy(request),
    }


def website_graph(request) -> dict[str, Any]:
    """WebSite entity.

    No SearchAction: `/catalog/?q=` never was a search page (catalog ignores
    `q`), Googlebot crawled the literal `{search_term_string}` URL and filed it
    as a duplicate of /catalog/. Sitelinks search box is deprecated anyway.
    """
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": ORG_NAME,
        "url": absolute_uri(request, "/"),
    }


def breadcrumb_graph(
    request, crumbs: list[tuple[str, str | None]]
) -> dict[str, Any]:
    """crumbs: list of (name, path_or_None). Last item may have path None = current URL."""
    elements = []
    for position, (name, path) in enumerate(crumbs, start=1):
        item_url = absolute_uri(request, path) if path else canonical_url(request)
        elements.append(
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": item_url,
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": elements,
    }


def _offer_price(attr) -> float | int | None:
    if attr.custom_attribute:
        if attr.custom_price is None:
            return None
        price = float(attr.custom_price)
        return int(price) if price == int(price) else price
    total = attr.get_total_price()
    if total is None:
        return None
    if isinstance(total, Decimal):
        total = float(total)
    return total


def _price_valid_until() -> str:
    return (timezone.now() + timedelta(days=PRICE_VALID_DAYS)).date().isoformat()


# Google product taxonomy paths. GSC "Merchant listings" flagged our raw
# category titles ("Турецькі") as an invalid `category` value: Google wants
# its own taxonomy string, not a shop label.
GOOGLE_CATEGORY_RUGS = "Home & Garden > Decor > Rugs"
GOOGLE_CATEGORY_BATH_MATS = "Home & Garden > Bathroom Accessories > Bath Mats & Rugs"
GOOGLE_CATEGORY_DOOR_MATS = "Home & Garden > Decor > Door Mats"
_CATEGORY_SLUG_TO_GOOGLE = {
    "dlia-vanni": GOOGLE_CATEGORY_BATH_MATS,
    "pid-dveri": GOOGLE_CATEGORY_DOOR_MATS,
}


def _google_product_category(product) -> str:
    slugs = {c.slug for c in product.categories.all()}
    for slug, path in _CATEGORY_SLUG_TO_GOOGLE.items():
        if slug in slugs:
            return path
    return GOOGLE_CATEGORY_RUGS


def _attach_merchant_offer_fields(offers: dict[str, Any], request) -> None:
    # validFrom: GSC lists it as a missing (non-critical) offer field.
    offers["validFrom"] = timezone.now().date().isoformat()
    offers["priceValidUntil"] = _price_valid_until()
    price = offers.get("price", offers.get("lowPrice"))
    shipping = offer_shipping_details(price)
    if shipping is not None:
        offers["shippingDetails"] = shipping
    offers["hasMerchantReturnPolicy"] = merchant_return_policy(request)


def _product_color(product) -> str | None:
    if product.active_color and (product.active_color.title or "").strip():
        return product.active_color.title.strip()
    return None


def _product_group_name(product) -> str:
    group = product.color_group
    if group and (group.name or "").strip():
        return group.name.strip()
    title = (product.title or "").strip()
    from project.merchant_feed import strip_title_colors

    # Colour words named in the title ("Килим овальний сірий Mira 24031"):
    # the group spans colours, so its name must not carry one of them.
    stripped = strip_title_colors(title)
    if len(stripped.split()) > 1 and stripped != title:
        return stripped
    color = _product_color(product)
    if color:
        for sep in (f" ({color})", f" — {color}", f" - {color}", f" {color}"):
            if title.endswith(sep):
                trimmed = title[: -len(sep)].strip()
                if trimmed:
                    return trimmed
    return title or ORG_NAME


def _is_placeholder_image(field) -> bool:
    # products/default.png is the upload placeholder. Google calls it a
    # generic image and refuses the merchant listing, so it is never offered.
    name = getattr(field, "name", "") or getattr(field, "url", "") or ""
    return str(name).endswith("default.png")


def _image_urls(request, product, images=None) -> list[str]:
    urls: list[str] = []
    if product.image and not _is_placeholder_image(product.image):
        url = absolute_uri(request, product.image.url)
        if url:
            urls.append(url)
    for img in images or []:
        field = getattr(img, "image", None)
        if field and not _is_placeholder_image(field):
            url = absolute_uri(request, field.url)
            if url and url not in urls:
                urls.append(url)
    return urls


def _size_label(attr) -> str:
    # Same "120x200 см" wording as the Merchant feed, so a listing built from
    # the feed and one built from the page describe one size the same way.
    from project.merchant_feed import format_size

    size = getattr(attr, "size", None)
    title = getattr(size, "title", None) if size is not None else None
    return format_size(title if isinstance(title, str) else "")


def _availability(in_stock: bool) -> str:
    return "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock"


def _list_price(attr) -> int | float | None:
    """The crossed-out price of a discounted size, None without a real discount."""
    from catalog.promotions import is_real_discount

    if not is_real_discount(attr):
        return None
    return attr.price


def _sale_end(product, rows) -> Any:
    """End of the running sale, looked up only when some size is discounted."""
    if not any(_list_price(attr) is not None for attr, _price, _stock in rows):
        return None
    from catalog.promotions import sale_end_for

    return sale_end_for(product)


def _single_offer(
    request, url: str, price, in_stock: bool, attr=None, sale_end=None
) -> dict[str, Any]:
    offer: dict[str, Any] = {
        "@type": "Offer",
        "url": url,
        "priceCurrency": "UAH",
        "price": price,
        "availability": _availability(in_stock),
        "itemCondition": "https://schema.org/NewCondition",
        "seller": {"@type": "Organization", "name": ORG_NAME},
    }
    _attach_merchant_offer_fields(offer, request)
    list_price = _list_price(attr)
    if list_price is not None:
        # Google shows the old price crossed out only when it is given as a
        # StrikethroughPrice next to the (discounted) `price`.
        offer["priceSpecification"] = {
            "@type": "UnitPriceSpecification",
            "priceType": "https://schema.org/StrikethroughPrice",
            "price": list_price,
            "priceCurrency": "UAH",
        }
        if sale_end is not None:
            # The sale price holds until the sale ends (ProductSale.date_end,
            # always in the future here, see catalog.promotions).
            offer["priceValidUntil"] = timezone.localtime(sale_end).date().isoformat()
    return offer


def _product_details(request, product) -> dict[str, Any]:
    """Properties shared by every size of one product page.

    On a ProductGroup they sit on the group (Google: common properties go on
    the group, variant-specific ones on each Product).
    """
    description = fix_utf8_mojibake(
        strip_tags(
            product.meta_description or product.description or product.title or ""
        )
    )[:5000]
    data: dict[str, Any] = {
        "description": description,
        "brand": {"@type": "Brand", "name": ORG_NAME},
        "category": _google_product_category(product),
    }

    # Approved only. The create endpoint accepts anonymous POSTs, so anything
    # else here would let a stranger set the star rating Google shows for a
    # product — and unverifiable ratings in structured data are what earns a
    # manual action, which costs every rich result on the site, not just stars.
    from catalog.models import ProductReview

    reviews = list(product.reviews.filter(status=ProductReview.Status.APPROVED))
    if reviews:
        ratings = [r.rating for r in reviews if r.rating]
        if ratings:
            data["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": round(sum(ratings) / len(ratings), 1),
                "reviewCount": len(ratings),
                "bestRating": 5,
                "worstRating": 1,
            }
        # `datePublished` is on Google's recommended list and was missing.
        # There is deliberately no "verified purchase" property here: the
        # review-snippet schema has none, so inventing one would add bytes
        # nothing reads. The badge stays a thing we show to humans, where it
        # affects whether they believe the review.
        data["review"] = [
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": r.name},
                "datePublished": r.created.date().isoformat(),
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": r.rating,
                    "bestRating": 5,
                    "worstRating": 1,
                },
                **(
                    {"reviewBody": r.content}
                    if (r.content or "").strip()
                    else {}
                ),
            }
            for r in reviews[:20]
        ]

    from project.merchant_feed import _clean as _feed_clean, product_color

    spec_color = None
    specs: list[tuple[str, str]] = []  # cleaned like merchant_feed.product_specs
    for row in product.product_specs.select_related(
        "specification", "spec_value"
    ).all():
        if not row.specification or not row.spec_value:
            continue
        name = (row.specification.title or "").strip()
        value = (row.spec_value.title or "").strip()
        if not name or not value:
            continue
        specs.append((_feed_clean(name), _feed_clean(value)))
        data.setdefault("additionalProperty", []).append(
            {
                "@type": "PropertyValue",
                "name": name,
                "value": value,
            }
        )
        name_l = name.lower()
        if any(k in name_l for k in ("матеріал", "склад", "материал")):
            data["material"] = value
        if spec_color is None and any(
            k in name_l for k in ("колір", "цвет", "color")
        ):
            spec_color = value

    # Same colour as the Merchant feed item (title colours, then active_color,
    # then the colour spec), so schema and feed never disagree. Local import:
    # merchant_feed imports this module. No colour known, no `color` key.
    color = product_color(product, specs) or spec_color
    if color:
        data["color"] = color
    return data


def _fixed_size_offers(product) -> list[tuple[Any, float | int, bool]]:
    """(attr, price, in_stock) for every sellable fixed size, in shop order.

    Custom sizes are priced per m², which is not a price anyone pays, and
    merchant listings need a real price above zero, so they are left out.
    """
    out = []
    for attr in product.product_attr.select_related("size").order_by(
        "sort_order", "pk"
    ):
        if attr.custom_attribute:
            continue
        price = _offer_price(attr)
        if price is None or price <= 0:
            continue
        out.append((attr, price, (attr.quantity or 0) > 0))
    return out


def _build_product_node(
    request, product, images=None, *, with_context: bool = True
) -> dict[str, Any] | None:
    """Plain Product for a page that sells one thing at one price.

    Also the fallback for a product sold only by custom size (price per m²):
    the old AggregateOffer/Offer shape, since it has no fixed size to list.
    """
    product_url = absolute_uri(request, product.get_absolute_url())
    fixed = _fixed_size_offers(product)

    if len(fixed) == 1:
        # One real size: one Offer, even if a per-m² custom size sits next to
        # it (mixing the two into an AggregateOffer made a fake price range).
        attr, price, in_stock = fixed[0]
        offers = _single_offer(
            request, product_url, price, in_stock,
            attr=attr, sale_end=_sale_end(product, fixed),
        )
        low = high = price
        prices = [price]
    else:
        attrs = list(
            product.product_attr.select_related("size").order_by("sort_order", "pk")
        )
        prices = []
        in_stock = False
        for attr in attrs:
            price = _offer_price(attr)
            if price is not None:
                prices.append(price)
            if (attr.quantity or 0) > 0:
                in_stock = True
        if not prices:
            return None
        low = min(prices)
        high = max(prices)

    if len(prices) == 1 and len(fixed) != 1:
        offers = _single_offer(request, product_url, low, in_stock)
    elif len(fixed) != 1:
        offers = {
            "@type": "AggregateOffer",
            "url": product_url,
            "priceCurrency": "UAH",
            "lowPrice": low,
            "highPrice": high,
            "offerCount": len(prices),
            "availability": _availability(in_stock),
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": ORG_NAME},
        }
        _attach_merchant_offer_fields(offers, request)

    data: dict[str, Any] = {
        "@type": "Product",
        "name": product.title,
        "sku": str(product.pk),
        "url": product_url,
        "offers": offers,
    }
    if len(fixed) == 1:
        # Same id as the Merchant feed item, so Google can tie the two.
        data["sku"] = f"{product.pk}-{fixed[0][0].pk}"
        size = _size_label(fixed[0][0])
        if size:
            data["size"] = size
    if with_context:
        data = {"@context": "https://schema.org", **data}

    image_urls = _image_urls(request, product, images)
    if image_urls:
        data["image"] = image_urls if len(image_urls) > 1 else image_urls[0]
    data.update(_product_details(request, product))
    return data


def _size_url(product, attr) -> str:
    from project.merchant_feed import variant_link

    return variant_link(product, attr)


def _selected_size_node(request, product, images, row) -> dict[str, Any]:
    attr, price, in_stock = row
    size = _size_label(attr)
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"{product.title} {size}".strip(),
        "sku": f"{product.pk}-{attr.pk}",
        "url": absolute_uri(request, product.get_absolute_url()),
        "offers": _single_offer(
            request, _size_url(product, attr), price, in_stock,
            attr=attr, sale_end=_sale_end(product, [row]),
        ),
    }
    if size:
        data["size"] = size
    image_urls = _image_urls(request, product, images)
    if image_urls:
        data["image"] = image_urls if len(image_urls) > 1 else image_urls[0]
    data.update(_product_details(request, product))
    return data


def _color_siblings(product) -> list[Any]:
    group = getattr(product, "color_group", None)
    if not group:
        return []
    variants = list(group.variants.select_related("active_color").order_by("pk"))
    if len(variants) <= 1:
        return []
    return [v for v in variants if v.pk != product.pk]


def product_graph(
    request, product, images=None, selected_attr=None
) -> dict[str, Any] | None:
    """Product JSON-LD for a PDP.

    One price, one colour: a plain Product with a single Offer.

    Several sizes and/or colour siblings: a ProductGroup whose hasVariant
    holds one Product + Offer per size of this page, and a bare {"url"} for
    every colour sibling (Google's multi-page variant pattern: full variants
    for this page, url-only references to the variants on other pages).

    Why not AggregateOffer, which this used to emit for every multi-size
    rug (41 of 99 pages): merchant listings do not accept it, and Google says
    not to use it for variants. Those pages were valid Product snippets at
    best and never merchant listings. The colour pages were worse: their
    sibling stubs were Products with no offers, each one an invalid item.

    `selected_attr` (the page was opened as `?size=<attr.pk>`, which is the
    link the Merchant feed gives every size): a plain Product with one Offer
    at that size's price and URL, so Merchant Center's landing-page price
    check reads exactly the price of the item it is checking.
    """
    fixed = _fixed_size_offers(product)
    if selected_attr is not None:
        chosen = [row for row in fixed if row[0].pk == selected_attr.pk]
        if chosen:
            return _selected_size_node(request, product, images, chosen[0])
    siblings = _color_siblings(product)

    if not fixed or (len(fixed) == 1 and not siblings):
        return _build_product_node(request, product, images=images, with_context=True)

    product_url = absolute_uri(request, product.get_absolute_url())
    image_urls = _image_urls(request, product, images)
    details = _product_details(request, product)
    color = details.pop("color", None)

    if siblings:
        group_id = f"cg-{product.color_group.pk}"
        group_name = _product_group_name(product)
    else:
        # Matches the feed's item_group_id.
        group_id = str(product.pk)
        group_name = (product.title or "").strip() or ORG_NAME

    varies_by = []
    if len(fixed) > 1:
        varies_by.append("https://schema.org/size")
    if siblings:
        varies_by.append("https://schema.org/color")

    has_variant: list[dict[str, Any]] = []
    sale_end = _sale_end(product, fixed)
    for attr, price, in_stock in fixed:
        size = _size_label(attr)
        # `?size=<attr.pk>` opens the page with this size chosen (see
        # catalog.views._selected_size_attr); the canonical stays bare. Same
        # URL the Merchant feed links, so feed item and offer agree.
        offer_url = _size_url(product, attr) if len(fixed) > 1 else product_url
        variant: dict[str, Any] = {
            "@type": "Product",
            "name": f"{product.title} {size}".strip(),
            "sku": f"{product.pk}-{attr.pk}",
            "inProductGroupWithID": group_id,
            "offers": _single_offer(
                request, offer_url, price, in_stock, attr=attr, sale_end=sale_end
            ),
        }
        if size:
            variant["size"] = size
        if color:
            variant["color"] = color
        if image_urls:
            variant["image"] = image_urls if len(image_urls) > 1 else image_urls[0]
        has_variant.append(variant)

    for sibling in siblings:
        url = absolute_uri(request, sibling.get_absolute_url())
        if url:
            has_variant.append({"url": url})

    product_group: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "ProductGroup",
        "name": group_name,
        "productGroupID": group_id,
        "variesBy": varies_by,
        **details,
        "hasVariant": has_variant,
    }
    if not siblings:
        # Single-page group: one canonical URL. Multi-page groups have none.
        product_group["url"] = product_url
    if image_urls:
        product_group["image"] = image_urls[0]
    return product_group


def article_graph(request, article) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article.title,
        "description": strip_tags(
            fix_utf8_mojibake(
                article.meta_description
                or (article.description or "")[:300]
                or article.title
            )
        ),
        "mainEntityOfPage": absolute_uri(request, article.get_absolute_url()),
        "author": {"@type": "Organization", "name": ORG_NAME},
        "publisher": {
            "@type": "Organization",
            "name": ORG_NAME,
            "logo": {
                "@type": "ImageObject",
                "url": absolute_uri(request, "/static/utils/assets/LogoBlack.svg"),
            },
        },
    }
    if article.image:
        data["image"] = absolute_uri(request, article.image.url)
    if article.created:
        # published_at, not created: a draft written in March and
        # published in July is a July article, and claiming otherwise
        # makes it look stale the day it appears.
        published = getattr(article, "published_at", None) or article.created
        data["datePublished"] = published.isoformat()
    # A scheduled article is saved (updated) before it goes live, so
    # updated < published_at; Google reads a modified date earlier than the
    # publish date as an error. Modified is never earlier than published.
    modified = article_modified_at(article)
    if modified:
        data["dateModified"] = modified.isoformat()
    return data


def article_modified_at(article):
    """Latest of ``updated`` and ``published_at`` (None when both are empty).

    Shared by Article JSON-LD, article:modified_time and the sitemap lastmod.
    """
    dates = [
        d
        for d in (getattr(article, "updated", None), getattr(article, "published_at", None))
        if d
    ]
    return max(dates) if dates else None


def faq_graph(qa_items: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in qa_items
        ],
    }


def _delivery_faq_answer() -> str:
    try:
        from project.free_shipping import get_shop_settings

        settings = get_shop_settings()
        if settings.free_shipping_enabled:
            return (
                f"Доставляємо Новою Поштою по Україні. Безкоштовна доставка від "
                f"{settings.free_shipping_threshold} грн "
                "(умови можуть уточнюватись на сторінці «Доставка і оплата»)."
            )
    except Exception:
        pass
    return (
        "Доставляємо Новою Поштою по Україні. "
        "Усі деталі є на сторінці «Доставка і оплата»."
    )


def get_faq_items() -> list[tuple[str, str]]:
    """Shared FAQ copy for HTML + JSON-LD (threshold from ShopSettings)."""
    return [
        (
            "Які матеріали використовуються для виготовлення килимів?",
            "Майже всі наші килими з поліпропілену. Є кілька моделей з поліестеру і з гуми. "
            "Точний склад є в блоці «Характеристики» на сторінці килима.",
        ),
        (
            "Як вибрати розмір килима для кімнати?",
            "Виміряйте вільну частину підлоги і залиште від стін та меблів 20-40 см. "
            "У вітальню часто беруть килим під передні ніжки дивана. У дитячу беруть такий, "
            "щоб накрити місце для ігор. Усі розміри є на сторінці килима.",
        ),
        (
            "Як правильно доглядати за килимом?",
            "Пилососьте килим регулярно, за напрямком ворсу, і не лийте багато води. "
            "Свіжу пляму приберіть м’яким засобом для текстилю. Якщо пляма стара або велика, "
            "краще віддати килим у хімчистку.",
        ),
        (
            "Які умови доставки?",
            _delivery_faq_answer(),
        ),
        (
            "Як оплатити замовлення?",
            "Можна оплатити онлайн через LiqPay на сайті або іншими способами, "
            "які є при оформленні. Усі деталі є на сторінці «Доставка і оплата».",
        ),
        (
            "Чи можна повернути килим?",
            "Так, за умовами повернення на сайті. Збережіть вигляд килима і чек. "
            "Як саме повернути, написано на сторінці «Повернення».",
        ),
    ]

