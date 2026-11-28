"""What the site chat bot can do: read the catalog, the cart, Nova Poshta,
and prepare an order card.

Every fact the bot tells a buyer (price, size, stock, delivery) comes from
here, never from the model. Nothing here places an order: `prepare_order`
only stores a draft. The order is created by the buyer's own click on the
card, through the same /api/create-order/ the checkout form uses.
"""

from __future__ import annotations

import re
import secrets
from django.db.models import Q

MAX_RESULTS = 6
PHONE_RE = re.compile(r"\D")


# ── tool schemas (Messages API) ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Пошук килимів у каталозі магазину. Повертає товари в наявності з "
            "розмірами (size_id), цінами і посиланнями. Шукай короткими словами: "
            "колір, форма, матеріал, кімната, розмір (200x300 або 2х3)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Слова для пошуку, напр. «сірий овальний 160x230».",
                },
                "max_price": {"type": "integer", "description": "Максимальна ціна, грн."},
                "min_price": {"type": "integer", "description": "Мінімальна ціна, грн."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_product",
        "description": "Повна інформація про один товар: опис, характеристики, усі розміри з цінами.",
        "input_schema": {
            "type": "object",
            "properties": {"product_id": {"type": "integer"}},
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "shop_info",
        "description": "Умови магазину: доставка, оплата, повернення, контакти і графік, килими під індивідуальний розмір (custom).",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": ["delivery", "payment", "returns", "contacts", "custom"],
                }
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
    {
        "name": "show_ar",
        "description": (
            "Показати покупцю примірку килима вдома в 3D/AR (тільки для товарів з ar: true). "
            "На телефоні покупець побачить кнопку, на комп'ютері QR-код для телефона."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer"},
                "size": {"type": "string", "description": "Розмір, напр. 2.0х3.0, якщо обраний."},
            },
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "view_cart",
        "description": "Що зараз у кошику покупця, сума і чи безкоштовна доставка.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "add_to_cart",
        "description": (
            "Додати розмір товару в кошик покупця. Тільки коли покупець прямо "
            "попросив додати або замовити саме цей товар і розмір."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "size_id": {"type": "integer", "description": "size_id з search_products/get_product."},
                "quantity": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["size_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remove_from_cart",
        "description": "Прибрати розмір товару з кошика.",
        "input_schema": {
            "type": "object",
            "properties": {"size_id": {"type": "integer"}},
            "required": ["size_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_city",
        "description": "Знайти населений пункт для доставки Новою Поштою. Повертає city_id.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Назва міста чи села."}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_warehouse",
        "description": (
            "Знайти відділення Нової Пошти в населеному пункті. query: номер "
            "відділення або вулиця; порожній, щоб побачити перші відділення."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city_id": {"type": "integer"},
                "query": {"type": "string"},
            },
            "required": ["city_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "request_stock",
        "description": (
            "Залишити заявку на розмір, якого немає в наявності (sold_out). Менеджер "
            "передзвонить, коли привезуть, або запропонує схожий. Перед викликом збери "
            "ім'я і телефон і коротко перепитай покупця, чи все правильно."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "size_id": {"type": "integer", "description": "size_id з sold_out."},
                "full_name": {"type": "string"},
                "phone": {"type": "string"},
                "email": {"type": "string", "description": "Необов'язково."},
            },
            "required": ["size_id", "full_name", "phone"],
            "additionalProperties": False,
        },
    },
    {
        "name": "request_callback",
        "description": (
            "Заявка на дзвінок менеджера, коли в чаті не вирішити: килим під індивідуальний "
            "розмір, довга доріжка, опт, складне питання. Збери ім'я і телефон, коротко "
            "перепитай і опиши запит одним-двома реченнями."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "full_name": {"type": "string"},
                "phone": {"type": "string"},
                "request": {"type": "string", "description": "Що потрібно покупцю, з розмірами."},
            },
            "required": ["full_name", "phone", "request"],
            "additionalProperties": False,
        },
    },
    {
        "name": "prepare_order",
        "description": (
            "Показати покупцю картку підтвердження замовлення з того, що в "
            "кошику. Викликай, коли є ім'я і прізвище, телефон, city_id, "
            "warehouse_id і спосіб оплати. Замовлення НЕ створюється: покупець "
            "сам натискає «Підтвердити» на картці."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "full_name": {"type": "string", "description": "Ім'я і прізвище отримувача."},
                "phone": {"type": "string"},
                "city_id": {"type": "integer"},
                "warehouse_id": {"type": "integer"},
                "payment": {
                    "type": "string",
                    "enum": ["cash", "card"],
                    "description": "cash: при отриманні; card: онлайн карткою.",
                },
                "email": {"type": "string", "description": "Необов'язково."},
                "comment": {"type": "string", "description": "Необов'язково."},
            },
            "required": ["full_name", "phone", "city_id", "warehouse_id", "payment"],
            "additionalProperties": False,
        },
    },
]


class ToolContext:
    """Per-request state the tools share: the request (session cart) and
    what the reply should carry to the widget."""

    def __init__(self, request, conversation):
        self.request = request
        self.conversation = conversation
        self.products: dict[int, dict] = {}
        self.order_card: dict | None = None
        self.cart_changed = False
        self.cart_events: list[dict] = []
        self.ar_card: dict | None = None


# ── helpers ──────────────────────────────────────────────────────────────────


def _abs_image(product) -> str:
    from catalog.thumbnails import thumbnail_url

    field = product.image
    if not field or (getattr(field, "name", "") or "").endswith("default.png"):
        # No catalog photo: the first gallery photo, as on the product page.
        first = next(iter(product.images.all()), None)
        field = first.image if first else None
    try:
        return thumbnail_url(field, 240) or "" if field else ""
    except Exception:
        return ""


def _sold_out(product) -> list[dict]:
    """Sizes that exist but are not in stock: the buyer can leave a request."""
    return [
        {"size_id": a.pk, "size": a.size.title if a.size else ""}
        for a in product.product_attr.all()
        if not a.custom_attribute and not a.in_stock
    ]


def _ar_ready(product) -> bool:
    from catalog.models import Product

    return getattr(product, "ar_status", None) == Product.AR_STATUS_READY


def _sizes(product) -> list[dict]:
    rows = []
    for attr in product.product_attr.all():
        if attr.custom_attribute or attr.price is None or not attr.in_stock:
            continue
        price = attr.get_total_price()
        rows.append(
            {
                "size_id": attr.pk,
                "size": attr.size.title if attr.size else "",
                "price": int(round(float(price))),
                "old_price": int(attr.price) if attr.discount else None,
            }
        )
    return rows


def _has_custom(product) -> bool:
    return any(a.custom_attribute for a in product.product_attr.all())


def _card(product) -> dict:
    sizes = _sizes(product)
    return {
        "id": product.pk,
        "title": product.title,
        "url": product.get_absolute_url(),
        "image": "",
        "price_from": min((s["price"] for s in sizes), default=None),
        "sizes": sizes,
        "sold_out": _sold_out(product),
        "cut_to_length": _has_custom(product),
        "ar": _ar_ready(product),
    }


def _product_qs():
    from catalog.models import Product

    return Product.objects.prefetch_related("product_attr__size", "colors", "images")


def _remember(ctx: ToolContext, card: dict):
    ctx.products[card["id"]] = card


def _cart_summary(request) -> dict:
    from cart.utils import get_cart_readonly
    from project.free_shipping import free_shipping_for_total

    cart = get_cart_readonly(request)
    items = []
    for cp in cart.cart_products.select_related("product_attr__product", "product_attr__size"):
        attr = cp.product_attr
        items.append(
            {
                "size_id": attr.pk,
                "title": attr.product.title if attr.product else "",
                "size": attr.size.title if attr.size else (f"{cp.length} м" if cp.length else ""),
                "quantity": cp.quantity,
                "line_total": cp.cart_product_total_price(),
            }
        )
    total = cart.get_total_price() if items else 0
    fs = free_shipping_for_total(total)
    return {
        "items": items,
        "total": total,
        "free_delivery": fs["qualifies"],
        "to_free_delivery": fs["remaining"] if fs["enabled"] else None,
        "delivery_from": fs["delivery_from_price"],
    }


def normalize_phone(raw: str) -> str | None:
    digits = PHONE_RE.sub("", raw or "")
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    elif len(digits) == 9:
        digits = "380" + digits
    if len(digits) == 12 and digits.startswith("380"):
        return "+" + digits
    return None


# ── tool implementations ─────────────────────────────────────────────────────


def search_products(ctx: ToolContext, query: str, max_price=None, min_price=None):
    from catalog.filters import search_tokens, token_q
    from catalog.models import Product

    tokens = search_tokens(query)[:6]
    qs = _product_qs()
    if tokens:
        # One query per word (see catalog.filters.matching_product_ids).
        per_token = [
            set(Product.admin_objects.filter(token_q(t)).values_list("pk", flat=True).order_by().distinct())
            for t in tokens
        ]
        ids = set.intersection(*per_token)
        if not ids and len(tokens) > 1:
            # Not every word matched one rug: keep the ones matching most words.
            scores: dict[int, int] = {}
            for found_ids in per_token:
                for pk in found_ids:
                    scores[pk] = scores.get(pk, 0) + 1
            if scores:
                best = max(scores.values())
                ids = {pk for pk, n in scores.items() if n == best}
        found = list(qs.filter(pk__in=ids)[:40])
    else:
        found = list(qs[:40])

    results = []
    for product in found:
        card = _card(product)
        prices = [s["price"] for s in card["sizes"]]
        if max_price and not any(p <= int(max_price) for p in prices):
            continue
        if min_price and not any(p >= int(min_price) for p in prices):
            continue
        if not card["sizes"] and not card["cut_to_length"] and not card["sold_out"]:
            continue
        results.append(card)
    # In stock first; sold-out rugs stay findable for a stock request.
    results.sort(key=lambda c: 0 if (c["sizes"] or c["cut_to_length"]) else 1)
    results = results[:MAX_RESULTS]
    by_pk = {p.pk: p for p in found}
    for card in results:
        card["image"] = _abs_image(by_pk[card["id"]])
        _remember(ctx, card)
    if not results:
        return {"found": 0, "hint": "Нічого не знайшлось. Спробуй менше слів або інші слова."}
    return {
        "found": len(results),
        "products": [
            {k: card[k] for k in ("id", "title", "url", "price_from", "sizes", "sold_out", "cut_to_length", "ar")}
            for card in results
        ],
    }


def get_product(ctx: ToolContext, product_id: int):
    from django.utils.html import strip_tags

    from catalog.models import Product

    product = (
        Product.admin_objects.prefetch_related(
            "product_attr__size", "colors", "images", "product_specs__specification", "product_specs__spec_value"
        )
        .filter(pk=product_id)
        .first()
    )
    if not product:
        return {"error": "Товар не знайдено або його немає в наявності."}
    card = _card(product)
    card["image"] = _abs_image(product)
    _remember(ctx, card)
    specs = {}
    for ps in product.product_specs.all():
        if ps.specification and ps.spec_value:
            specs[ps.specification.title] = ps.spec_value.title
    description = re.sub(r"\s+", " ", strip_tags(product.description or "")).strip()[:900]
    return {
        **{k: card[k] for k in ("id", "title", "url", "sizes", "sold_out", "cut_to_length", "ar")},
        "colors": [c.title for c in product.colors.all()],
        "specs": specs,
        "description": description,
        "note": (
            "Цей килим ріжемо на потрібну довжину: такий розмір покупець обирає "
            "на сторінці товару, у чаті додати не можна."
            if card["cut_to_length"]
            else ""
        ),
    }


def shop_info(ctx: ToolContext, topic: str):
    from project.free_shipping import delivery_terms
    from project.seo_jsonld import ORG_EMAIL, ORG_PHONE

    t = delivery_terms()
    if topic == "delivery":
        free = (
            f"Від {t['threshold']} грн доставка безкоштовна, її оплачуємо ми. "
            "Сума рахується за товари в кошику, уже зі знижкою."
            if t["free_enabled"]
            else ""
        )
        return {
            "text": (
                "Відправляємо Новою Поштою по всій Україні, у відділення. "
                "У поштомати килими не поміщаються. "
                f"{free} Якщо дешевше, доставку оплачує покупець за тарифами Нової Пошти, "
                f"від {t['from_price']} грн, ціна залежить від ваги і розміру. "
                f"Відправляємо в день замовлення або {t['handling_text']}, "
                f"у дорозі зазвичай {t['transit_text']}. "
                "Інша служба доставки: можна домовитись по телефону."
            ),
            "page": "/delivery/",
        }
    if topic == "payment":
        return {
            "text": (
                "При отриманні: платите у відділенні Нової Пошти, Нова Пошта бере "
                "свою комісію, її платить покупець. Онлайн карткою через LiqPay "
                "одразу після оформлення. Килими, які ріжемо під ваш розмір, "
                "оплачуються наперед повністю."
            ),
            "page": "/delivery/",
        }
    if topic == "returns":
        return {
            "text": (
                f"Повернути можна протягом {t['return_days_text']}, не рахуючи дня покупки, "
                "якщо килимом не користувались, є ярлики, ціле пакування і документ про "
                "оплату. Килими, зроблені під ваш розмір, не повертаються. Доставку назад "
                "оплачує покупець, крім браку. Спершу треба подзвонити або написати нам."
            ),
            "page": "/refund/",
        }
    if topic == "custom":
        return {
            "text": (
                "Так, килими під індивідуальний розмір робимо на замовлення. Ціну і строк "
                "менеджер скаже після дзвінка. Такі килими оплачуються наперед повністю і не "
                "повертаються. Можна залишити заявку на дзвінок (request_callback)."
            ),
            "page": "/delivery/",
        }
    return {
        "phone": ORG_PHONE,
        "email": ORG_EMAIL,
        "hours": "Пн-Пт 9:00-18:00, субота і неділя вихідні",
        "address": "Тернопільська обл., м. Ланівці, вул. Незалежності 5а",
        "visit": "Приїхати можна, але краще спершу подзвонити, щоб потрібний килим точно чекав.",
        "page": "/contacts/",
    }


def view_cart(ctx: ToolContext):
    summary = _cart_summary(ctx.request)
    if not summary["items"]:
        return {"items": [], "text": "Кошик порожній."}
    return summary


def add_to_cart(ctx: ToolContext, size_id: int, quantity: int = 1):
    from cart.models import CartProduct
    from cart.utils import get_cart
    from catalog.models import ProductAttribute
    from project.merchant_feed import offer_id

    quantity = max(1, min(int(quantity or 1), 10))
    attr = ProductAttribute.objects.select_related("product", "size").filter(pk=size_id).first()
    if not attr or not attr.product:
        return {"error": "Такого розміру немає."}
    if attr.custom_attribute:
        return {"error": "Цей килим ріжемо на довжину, його додають на сторінці товару.",
                "url": attr.product.get_absolute_url()}
    if attr.price is None:
        return {"error": "У цього розміру немає ціни, його не можна замовити."}

    cart = get_cart(ctx.request)
    line = CartProduct.objects.filter(cart=cart, product_attr=attr).first()
    want = quantity + (line.quantity if line else 0)
    if want > (attr.quantity or 0):
        return {"error": f"Стільки немає. У наявності: {attr.quantity or 0} шт."}
    if line:
        line.quantity = want
        line.save(update_fields=["quantity", "updated"])
    else:
        CartProduct.objects.create(cart=cart, product_attr=attr, quantity=quantity)

    ctx.cart_changed = True
    price = float(attr.get_total_price() or 0)
    ctx.cart_events.append(
        {
            "event": "add_to_cart",
            "item": {
                "item_id": offer_id(attr.product, attr),
                "item_group_id": str(attr.product.pk),
                "item_name": attr.product.title,
                "item_brand": "mr.Carpet",
                "item_variant": attr.size.title if attr.size else "",
                "price": price,
                "quantity": quantity,
            },
        }
    )
    summary = _cart_summary(ctx.request)
    return {"added": f"{attr.product.title}, {attr.size.title if attr.size else ''}, {quantity} шт.", "cart": summary}


def remove_from_cart(ctx: ToolContext, size_id: int):
    from cart.models import CartProduct
    from cart.utils import get_cart_readonly

    cart = get_cart_readonly(ctx.request)
    if not cart:
        return {"error": "Кошик порожній."}
    deleted, _ = CartProduct.objects.filter(cart=cart, product_attr_id=size_id).delete()
    if not deleted:
        return {"error": "Цього розміру немає в кошику."}
    ctx.cart_changed = True
    return {"removed": True, "cart": _cart_summary(ctx.request)}


def find_city(ctx: ToolContext, name: str):
    from nova_poshta.models import Settlement

    query = (name or "").strip()
    if len(query) < 2:
        return {"error": "Напиши назву населеного пункту."}
    forms = {query, query[:1].upper() + query[1:]}
    q = Q()
    for form in forms:
        q |= Q(title__istartswith=form)
    rows = list(
        Settlement.objects.filter(q, warehouse__isnull=False)
        .select_related("type", "area")
        .distinct()
        .order_by("title")[:40]
    )
    exact = [s for s in rows if s.title.lower() == query.lower()]
    rows = (exact + [s for s in rows if s not in exact])[:8]
    if not rows:
        return {"found": 0, "hint": "Не знайшли такого населеного пункту з відділеннями Нової Пошти."}
    return {
        "cities": [
            {
                "city_id": s.pk,
                "title": s.title,
                "type": s.type.title if s.type else "",
                "area": s.area.title if s.area else "",
            }
            for s in rows
        ]
    }


def _warehouse_qs(city_id):
    from nova_poshta.models import Warehouse

    postomat = Q(type__title__icontains="поштомат") | Q(title__icontains="поштомат") | Q(title__icontains="Поштомат")
    return Warehouse.objects.filter(settlement_id=city_id).exclude(postomat)


def find_warehouse(ctx: ToolContext, city_id: int, query: str = ""):
    qs = _warehouse_qs(city_id)
    query = (query or "").strip()
    if query:
        number = re.search(r"\d+", query)
        if number:
            n = number.group(0)
            qs = qs.filter(Q(title__icontains=f"№{n}:") | Q(title__icontains=f"№{n} ") | Q(title__endswith=f"№{n}") | Q(title__icontains=f"№ {n}"))
        else:
            words = [w for w in re.split(r"\s+", query) if len(w) >= 3]
            for w in words[:3]:
                stem = w[:-1] if len(w) > 4 else w
                qs = qs.filter(Q(title__icontains=stem) | Q(title__icontains=stem.capitalize()))
    total = qs.count()
    rows = list(qs[:8])
    if not rows:
        return {"found": 0, "hint": "Не знайшли відділення. Запитай номер відділення або вулицю."}
    return {
        "total": total,
        "warehouses": [{"warehouse_id": w.pk, "title": w.title} for w in rows],
    }


# Spam guard for orders made in the chat. Real buyers place one order, maybe
# fix it once or twice; these stop a script from filling the admin with fakes.
MAX_CARDS_PER_CONVERSATION = 4
MAX_CARDS_PER_CLIENT_DAY = 8
MAX_CHAT_ORDERS_PER_CLIENT_DAY = 2
CALL_US = "Для ще одного замовлення подзвоніть нам: +380 96 398 88 75, або оформіть його на сторінці /checkout/."


def _order_card_limit(conversation) -> str | None:
    from datetime import timedelta

    from django.db.models import Sum
    from django.utils import timezone

    from .models import Conversation

    if (conversation.cards_shown or 0) >= MAX_CARDS_PER_CONVERSATION:
        return "Ліміт карток у цій розмові вичерпано. " + CALL_US
    if not conversation.client_hash:
        return None
    since = timezone.now() - timedelta(hours=24)
    mine = Conversation.objects.filter(client_hash=conversation.client_hash, updated__gte=since)
    if mine.filter(order__isnull=False).count() >= MAX_CHAT_ORDERS_PER_CLIENT_DAY:
        return "Сьогодні з цього пристрою вже оформлено кілька замовлень у чаті. " + CALL_US
    if (mine.aggregate(n=Sum("cards_shown"))["n"] or 0) >= MAX_CARDS_PER_CLIENT_DAY:
        return "Забагато спроб оформлення сьогодні. " + CALL_US
    return None


def prepare_order(
    ctx: ToolContext,
    full_name: str,
    phone: str,
    city_id: int,
    warehouse_id: int,
    payment: str,
    email: str = "",
    comment: str = "",
):
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    from nova_poshta.models import Settlement

    limit = _order_card_limit(ctx.conversation)
    if limit:
        return {"error": limit}
    summary = _cart_summary(ctx.request)
    if not summary["items"]:
        return {"error": "Кошик порожній. Спершу додай товар."}
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    if len(parts) < 2:
        return {"error": "Потрібні ім'я і прізвище отримувача, як у паспорті."}
    normalized = normalize_phone(phone)
    if not normalized:
        return {"error": "Телефон має бути український, напр. 0961234567."}
    email = (email or "").strip()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return {"error": "Email виглядає неправильно. Можна без нього."}
    city = Settlement.objects.filter(pk=city_id).first()
    warehouse = _warehouse_qs(city_id).filter(pk=warehouse_id).first()
    if not city or not warehouse:
        return {"error": "Не знайшли таке відділення в цьому населеному пункті."}
    if payment not in ("cash", "card"):
        return {"error": "Оплата: cash або card."}

    comment = re.sub(r"\s+", " ", comment or "").strip()[:300]
    draft = {
        "token": secrets.token_urlsafe(16),
        "name": parts[0],
        "surname": " ".join(parts[1:]),
        "phone": normalized,
        "email": email,
        "city": city.title,
        "address": warehouse.title,
        "payment_type": "liqpay" if payment == "card" else "cash",
        "message": ("Оформлено через чат-бот. " + comment).strip(),
        "comment": comment,
        "items": summary["items"],
        "total": summary["total"],
        "free_delivery": summary["free_delivery"],
        "delivery_from": summary["delivery_from"],
    }
    ctx.conversation.pending_order = draft
    ctx.conversation.cards_shown = (ctx.conversation.cards_shown or 0) + 1
    ctx.conversation.save(update_fields=["pending_order", "cards_shown", "updated"])
    ctx.order_card = draft
    return {
        "shown": True,
        "text": (
            "Покупцю показано картку з кнопкою «Підтвердити». Коротко попроси "
            "перевірити дані і натиснути кнопку. Сам замовлення не оформлюй."
        ),
    }


MAX_STOCK_REQUESTS_PER_CLIENT_DAY = 3


def request_stock(ctx: ToolContext, size_id: int, full_name: str, phone: str, email: str = ""):
    from datetime import timedelta

    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    from django.utils import timezone

    from catalog.models import ProductAttribute
    from project.models import StockInquiry

    attr = ProductAttribute.objects.select_related("product", "size").filter(pk=size_id).first()
    if not attr or not attr.product:
        return {"error": "Такого розміру немає."}
    if attr.in_stock:
        return {"error": "Цей розмір є в наявності, його можна просто додати в кошик."}
    name = re.sub(r"\s+", " ", full_name or "").strip()[:115]
    if len(name) < 2:
        return {"error": "Потрібне ім'я покупця."}
    normalized = normalize_phone(phone)
    if not normalized:
        return {"error": "Телефон має бути український, напр. 0961234567."}
    email = (email or "").strip()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return {"error": "Email виглядає неправильно. Можна без нього."}

    since = timezone.now() - timedelta(hours=24)
    recent = StockInquiry.objects.filter(phone=normalized, created__gte=since)
    if recent.filter(product_attr=attr).exists():
        return {"ok": True, "text": "Заявку на цей розмір уже прийнято, менеджер зателефонує."}
    if (
        recent.count() >= MAX_STOCK_REQUESTS_PER_CLIENT_DAY
        or _client_stock_requests(ctx) >= MAX_STOCK_REQUESTS_PER_CLIENT_DAY
    ):
        return {"error": "Сьогодні вже прийнято кілька заявок. Подзвоніть нам: +380 96 398 88 75."}

    inquiry = StockInquiry.objects.create(
        name=name,
        email=email,
        phone=normalized,
        product=attr.product,
        product_attr=attr,
    )
    ctx.conversation.stock_requests = (ctx.conversation.stock_requests or 0) + 1
    ctx.conversation.save(update_fields=["stock_requests", "updated"])
    _notify_stock_inquiry(inquiry)
    return {
        "ok": True,
        "text": (
            f"Заявку прийнято: {attr.product.title}, {inquiry.size_label}. "
            "Менеджер зателефонує, коли привезуть, або запропонує схожий килим."
        ),
    }


def request_callback(ctx: ToolContext, full_name: str, phone: str, request: str):
    from project.models import ContactRequest

    name = re.sub(r"\s+", " ", full_name or "").strip()[:115]
    if len(name) < 2:
        return {"error": "Потрібне ім'я покупця."}
    normalized = normalize_phone(phone)
    if not normalized:
        return {"error": "Телефон має бути український, напр. 0961234567."}
    text = re.sub(r"\s+", " ", request or "").strip()[:600]
    if len(text) < 5:
        return {"error": "Опиши, що потрібно покупцю."}
    if _client_stock_requests(ctx) >= MAX_STOCK_REQUESTS_PER_CLIENT_DAY:
        return {"error": "Сьогодні вже прийнято кілька заявок. Подзвоніть нам: +380 96 398 88 75."}

    contact = ContactRequest.objects.create(
        name=name,
        email="",
        text=f"Заявка з чат-бота на сайті. Телефон: {normalized}\n{text}",
    )
    ctx.conversation.stock_requests = (ctx.conversation.stock_requests or 0) + 1
    ctx.conversation.save(update_fields=["stock_requests", "updated"])
    try:
        from project.telegram_utils import notify_contact

        notify_contact(contact)
    except Exception:
        pass
    return {"ok": True, "text": "Заявку прийнято. Менеджер зателефонує в робочий час (Пн-Пт 9:00-18:00)."}


def _client_stock_requests(ctx) -> int:
    from datetime import timedelta

    from django.db.models import Sum
    from django.utils import timezone

    from .models import Conversation

    if not ctx.conversation.client_hash:
        return ctx.conversation.stock_requests or 0
    since = timezone.now() - timedelta(hours=24)
    return (
        Conversation.objects.filter(client_hash=ctx.conversation.client_hash, updated__gte=since)
        .aggregate(n=Sum("stock_requests"))["n"]
        or 0
    )


def _notify_stock_inquiry(inquiry):
    """The same letters and Telegram note as the site's «Запит наявності» form."""
    from project.email_utils import build_stock_inquiry_admin_email, build_stock_inquiry_customer_email
    from project.models import SMTPSettings
    from project.smtp_utils import send_smtp_mail_async
    from project.telegram_utils import notify_stock

    try:
        notify_to = SMTPSettings.load().server_email
    except Exception:
        notify_to = None
    try:
        if notify_to:
            subject, text, html = build_stock_inquiry_admin_email(inquiry)
            send_smtp_mail_async(subject, text, [notify_to], html_message=html)
        if inquiry.email:
            subject, text, html = build_stock_inquiry_customer_email(inquiry)
            send_smtp_mail_async(subject, text, [inquiry.email], html_message=html)
    except Exception:
        pass
    try:
        notify_stock(inquiry)
    except Exception:
        pass


def show_ar(ctx: ToolContext, product_id: int, size: str = ""):
    from urllib.parse import urlencode

    from catalog.models import Product

    product = Product.admin_objects.prefetch_related("product_attr__size", "images").filter(pk=product_id).first()
    if not product:
        return {"error": "Товар не знайдено."}
    if not _ar_ready(product):
        return {"error": "Для цього килима 3D-примірки ще немає."}
    sizes = [a.size.title for a in product.product_attr.all() if a.size and not a.custom_attribute]
    wanted = (size or "").replace("x", "х").replace("X", "х").strip()
    label = next((s_ for s_ in sizes if s_.replace("x", "х") == wanted), "") or (sizes[0] if sizes else "")
    base = product.get_absolute_url()
    params = {"view3d": "1", **({"size": label} if label else {})}
    ctx.ar_card = {
        "product_id": product.pk,
        "title": product.title,
        "image": _abs_image(product),
        "size": label,
        "link_3d": f"{base}?{urlencode(params)}",
        "link_ar": f"{base}?{urlencode({**params, 'ar': '1'})}",
    }
    return {
        "shown": True,
        "text": "Покупець бачить кнопку примірки (на компʼютері QR-код). Коротко поясни, що килим зʼявиться вдома в реальному розмірі.",
    }


HANDLERS = {
    "show_ar": show_ar,
    "request_stock": request_stock,
    "request_callback": request_callback,
    "search_products": search_products,
    "get_product": get_product,
    "shop_info": shop_info,
    "view_cart": view_cart,
    "add_to_cart": add_to_cart,
    "remove_from_cart": remove_from_cart,
    "find_city": find_city,
    "find_warehouse": find_warehouse,
    "prepare_order": prepare_order,
}


def run_tool(ctx: ToolContext, name: str, args: dict):
    handler = HANDLERS.get(name)
    if handler is None:
        return {"error": f"Невідомий інструмент {name}"}, True
    try:
        result = handler(ctx, **(args or {}))
    except TypeError as exc:
        return {"error": f"Неправильні параметри: {exc}"}, True
    is_error = isinstance(result, dict) and "error" in result
    return result, is_error
