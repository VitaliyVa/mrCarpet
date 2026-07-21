"""Server-rendered JSON-LD builders (SEO Phase 4 + 7 Merchant / variants)."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.html import strip_tags

from project.text_encoding import fix_utf8_mojibake

ORG_NAME = "mr.Carpet"
ORG_ALT = "Магазин Меблі Килими"
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
    return request.build_absolute_uri(value)


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


def offer_shipping_details() -> dict[str, Any] | None:
    """Free shipping OfferShippingDetails when enabled in ShopSettings."""
    try:
        from project.free_shipping import get_shop_settings

        settings = get_shop_settings()
        if not settings.free_shipping_enabled:
            return None
    except Exception:
        pass

    return {
        "@type": "OfferShippingDetails",
        "shippingRate": {
            "@type": "MonetaryAmount",
            "value": "0",
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
        "alternateName": ORG_ALT,
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


def breadcrumb_graph(
    request, crumbs: list[tuple[str, str | None]]
) -> dict[str, Any]:
    """crumbs: list of (name, path_or_None). Last item may have path None = current URL."""
    elements = []
    for position, (name, path) in enumerate(crumbs, start=1):
        item_url = absolute_uri(request, path) if path else request.build_absolute_uri()
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


def _attach_merchant_offer_fields(offers: dict[str, Any], request) -> None:
    offers["priceValidUntil"] = _price_valid_until()
    shipping = offer_shipping_details()
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
    color = _product_color(product)
    if color:
        for sep in (f" ({color})", f" — {color}", f" - {color}", f" {color}"):
            if title.endswith(sep):
                trimmed = title[: -len(sep)].strip()
                if trimmed:
                    return trimmed
    return title or ORG_NAME


def _build_product_node(
    request, product, images=None, *, with_context: bool = True
) -> dict[str, Any] | None:
    attrs = list(
        product.product_attr.select_related("size").order_by("sort_order", "pk")
    )
    prices: list[float | int] = []
    in_stock = False
    for attr in attrs:
        price = _offer_price(attr)
        if price is not None:
            prices.append(price)
        if (attr.quantity or 0) > 0:
            in_stock = True

    if not prices:
        return None

    image_urls: list[str] = []
    if product.image:
        url = absolute_uri(request, product.image.url)
        if url:
            image_urls.append(url)
    for img in images or []:
        if getattr(img, "image", None):
            url = absolute_uri(request, img.image.url)
            if url and url not in image_urls:
                image_urls.append(url)

    availability = (
        "https://schema.org/InStock"
        if in_stock
        else "https://schema.org/OutOfStock"
    )
    low = min(prices)
    high = max(prices)
    product_url = absolute_uri(request, product.get_absolute_url())

    if len(prices) == 1:
        offers: dict[str, Any] = {
            "@type": "Offer",
            "url": product_url,
            "priceCurrency": "UAH",
            "price": low,
            "availability": availability,
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": ORG_NAME},
        }
    else:
        offers = {
            "@type": "AggregateOffer",
            "url": product_url,
            "priceCurrency": "UAH",
            "lowPrice": low,
            "highPrice": high,
            "offerCount": len(prices),
            "availability": availability,
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": ORG_NAME},
        }
    _attach_merchant_offer_fields(offers, request)

    description = fix_utf8_mojibake(
        strip_tags(
            product.meta_description or product.description or product.title or ""
        )
    )[:5000]

    data: dict[str, Any] = {
        "@type": "Product",
        "name": product.title,
        "description": description,
        "sku": str(product.pk),
        "url": product_url,
        "brand": {"@type": "Brand", "name": ORG_NAME},
        "offers": offers,
    }
    if with_context:
        data = {"@context": "https://schema.org", **data}

    if image_urls:
        data["image"] = image_urls if len(image_urls) > 1 else image_urls[0]

    category = product.categories.first()
    if category:
        data["category"] = category.title

    color = _product_color(product)
    if color:
        data["color"] = color

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

    for row in product.product_specs.select_related(
        "specification", "spec_value"
    ).all():
        if not row.specification or not row.spec_value:
            continue
        name = (row.specification.title or "").strip()
        value = (row.spec_value.title or "").strip()
        if not name or not value:
            continue
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
        if "color" not in data and any(
            k in name_l for k in ("колір", "цвет", "color")
        ):
            data["color"] = value

    return data


def _variant_stub(request, variant) -> dict[str, Any]:
    stub: dict[str, Any] = {
        "@type": "Product",
        "sku": str(variant.pk),
        "url": absolute_uri(request, variant.get_absolute_url()),
        "name": variant.title,
    }
    color = _product_color(variant)
    if color:
        stub["color"] = color
    if variant.image:
        img = absolute_uri(request, variant.image.url)
        if img:
            stub["image"] = img
    return stub


def product_graph(
    request, product, images=None
) -> dict[str, Any] | list[Any] | None:
    """
    Product JSON-LD for PDP.
    Color variants (multi-URL): ProductGroup + nested hasVariant (Google multi-page).
    """
    node = _build_product_node(request, product, images=images, with_context=True)
    if not node:
        return None

    group = getattr(product, "color_group", None)
    if not group:
        return node

    variants = list(
        group.variants.select_related("active_color").order_by("pk")
    )
    if len(variants) <= 1:
        return node

    group_id = f"cg-{group.pk}"
    current = _build_product_node(
        request, product, images=images, with_context=False
    )
    if not current:
        return node

    current["inProductGroupWithID"] = group_id

    has_variant: list[dict[str, Any]] = []
    for variant in variants:
        if variant.pk == product.pk:
            has_variant.append(current)
        else:
            has_variant.append(_variant_stub(request, variant))

    product_group: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "ProductGroup",
        "@id": f"#product-group-{group_id}",
        "name": _product_group_name(product),
        "brand": {"@type": "Brand", "name": ORG_NAME},
        "productGroupID": group_id,
        "variesBy": ["https://schema.org/color"],
        "hasVariant": has_variant,
    }
    return [product_group]


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
    if article.updated:
        data["dateModified"] = article.updated.isoformat()
    return data


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
        "Деталі — на сторінці «Доставка і оплата»."
    )


def get_faq_items() -> list[tuple[str, str]]:
    """Shared FAQ copy for HTML + JSON-LD (threshold from ShopSettings)."""
    return [
        (
            "Які матеріали використовуються для виготовлення килимів?",
            "У асортименті mr.Carpet є килими з поліпропілену, вовни, бавовни та сумішей. "
            "Точний склад кожного товару вказаний у блоці «Характеристики» на сторінці килима.",
        ),
        (
            "Як вибрати розмір килима для кімнати?",
            "Виміряйте вільну зону підлоги й залиште відступ від стін/меблів 20–40 см. "
            "Для вітальні часто беруть килим під передню лінію дивана; у дитячій — "
            "щоб покрити ігрову зону. Розміри варіантів є в картці товару.",
        ),
        (
            "Як правильно доглядати за килимом?",
            "Регулярно пилососьте за ворсом, уникайте надлишку води. Локальні плями "
            "прибирайте м’яким засобом для текстилю. Для вовни й делікатних сумішей "
            "краще професійне чищення.",
        ),
        (
            "Які умови доставки?",
            _delivery_faq_answer(),
        ),
        (
            "Як оплатити замовлення?",
            "Можна оплатити онлайн через LiqPay на сайті або іншими способами, "
            "вказаними при оформленні. Деталі — на сторінці «Доставка і оплата».",
        ),
        (
            "Чи можна повернути килим?",
            "Так, згідно з умовами повернення на сайті. Збережіть товарний вигляд "
            "і чек; детальний порядок — на сторінці «Повернення».",
        ),
    ]

