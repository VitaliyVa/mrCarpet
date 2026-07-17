"""Server-rendered JSON-LD builders (SEO Phase 4)."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django.utils.html import strip_tags

ORG_NAME = "mr.Carpet"
ORG_ALT = "Магазин Меблі Килими"
ORG_EMAIL = "mr.carpet.shop@gmail.com"
ORG_PHONE = "+380963988875"
ORG_STREET = "вул. Незалежності 5а"
ORG_LOCALITY = "Ланівці"
ORG_REGION = "Тернопільська область"
ORG_COUNTRY = "UA"


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


def organization_graph(request) -> dict[str, Any]:
    logo = absolute_uri(request, "/static/utils/assets/LogoBlack.svg")
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": ORG_NAME,
        "alternateName": ORG_ALT,
        "url": absolute_uri(request, "/"),
        "logo": logo,
        "email": ORG_EMAIL,
        "telephone": ORG_PHONE,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": ORG_STREET,
            "addressLocality": ORG_LOCALITY,
            "addressRegion": ORG_REGION,
            "addressCountry": ORG_COUNTRY,
        },
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


def product_graph(request, product, images=None) -> dict[str, Any] | None:
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

    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.title,
        "description": strip_tags(
            product.meta_description or product.description or product.title or ""
        )[:5000],
        "sku": str(product.pk),
        "url": product_url,
        "brand": {"@type": "Brand", "name": ORG_NAME},
        "offers": offers,
    }
    if image_urls:
        data["image"] = image_urls if len(image_urls) > 1 else image_urls[0]

    category = product.categories.first()
    if category:
        data["category"] = category.title

    reviews = list(product.reviews.all())
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
        data["review"] = [
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": r.name},
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

    # Specs → schema (deterministic; never invent via LLM)
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
        if any(k in name_l for k in ("колір", "цвет", "color")):
            data["color"] = value

    # Free shipping from 800 UAH — matches storefront copy
    data["offers"]["shippingDetails"] = {
        "@type": "OfferShippingDetails",
        "shippingRate": {
            "@type": "MonetaryAmount",
            "value": "0",
            "currency": "UAH",
        },
        "shippingDestination": {
            "@type": "DefinedRegion",
            "addressCountry": "UA",
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

    return data


def article_graph(request, article) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article.title,
        "description": strip_tags(
            article.meta_description
            or (article.description or "")[:300]
            or article.title
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
        data["datePublished"] = article.created.isoformat()
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


# Shared FAQ copy for HTML + JSON-LD (Phase 4.4 / 5.1 minimum)
FAQ_ITEMS: list[tuple[str, str]] = [
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
        "Доставляємо Новою Поштою по Україні. Безкоштовна доставка від 800 грн "
        "(умови можуть уточнюватись на сторінці «Доставка і оплата»).",
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
