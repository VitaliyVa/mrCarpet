"""Order follow-up helpers for the shop Telegram chat.

* order_checks(order): warnings and hints shown under the «Нове замовлення»
  notification (wrong phone, parcel too long for a post box, repeat or
  previously cancelled buyer, last item in stock, ...).
* customer_message(order): ready text the manager copies into Viber,
  Telegram or SMS to confirm the order without a call.
* call_script(order): what to say when calling the buyer.
* order_keyboard(order) / handle_order_callback(cq): the two bot buttons.

Everything here is best effort: any failure returns an empty result, so the
order notification itself is never blocked.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import timedelta

from django.conf import settings as django_settings
from django.core import signing
from django.utils import timezone

logger = logging.getLogger(__name__)

CB_MESSAGE = "ordtx"
CB_CALL = "ordcl"
SIGN_SALT = "order-viber"
LINK_MAX_AGE = 60 * 60 * 24 * 30

# Nova Poshta limits (approximate, from NP rules as of 2026): post boxes hold
# parcels up to about 60 cm and 20 kg; branches «до N кг» take items up to
# about 120 cm on the longest side.
POST_BOX_MAX_CM = 60
POST_BOX_MAX_KG = 20
LIMITED_BRANCH_MAX_CM = 120
BIG_COD_SUM = 3000
FREE_SHIPPING_HINT_GAP = 500

_MOBILE_CODES = {
    "39", "50", "63", "66", "67", "68", "73", "77", "91", "92", "93", "94",
    "95", "96", "97", "98", "99",
}
_BRANCH_LIMIT_RE = re.compile(r"до\s*(\d+)\s*кг", re.IGNORECASE)


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def normalize_phone(phone: str | None) -> str:
    """'+380 73 209 59 12' / '073 209 5912' -> '380732095912' ('' if unknown)."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    elif len(digits) == 9:
        digits = "380" + digits
    return digits if len(digits) == 12 and digits.startswith("380") else ""


def is_mobile(phone: str | None) -> bool:
    digits = normalize_phone(phone)
    return bool(digits) and digits[3:5] in _MOBILE_CODES


# ---------------------------------------------------------------- items ---


def _product_params(product) -> dict:
    from project.merchant_feed import product_specs
    from project.prom_feed import _ROZETKA_SPEC_NAMES

    params = {}
    for name, value in product_specs(product):
        mapped = _ROZETKA_SPEC_NAMES.get(name.lower(), name)
        if mapped and mapped not in params:
            params[mapped] = value
    return params


def order_items(order) -> list[dict]:
    """[{title, size, quantity, length, last, ship}] for the order cart."""
    from project.merchant_feed import format_size
    from project.rozetka_logistics import logistics

    try:
        rows = order.cart.cart_products.select_related(
            "product_attr__product", "product_attr__size"
        )
    except Exception:
        return []
    items = []
    for cp in rows:
        attr = cp.product_attr
        product = getattr(attr, "product", None)
        size = format_size(attr.size.title if attr and attr.size else "")
        ship = None
        if product is not None and size:
            try:
                ship = logistics(product.title, size, _product_params(product))
            except Exception:
                ship = None
        items.append(
            {
                "title": getattr(product, "title", "") or "—",
                "size": size,
                "quantity": cp.quantity or 1,
                "length": cp.length,
                "last": bool(
                    attr is not None
                    and not getattr(attr, "custom_attribute", False)
                    and (attr.quantity or 0) <= 0
                ),
                "ship": ship,
            }
        )
    return items


def _parcel(items) -> tuple[float, int] | None:
    """(total kg, longest package side cm) or None when unknown."""
    known = [i for i in items if i["ship"]]
    if not known or len(known) != len(items):
        return None
    weight = sum(i["ship"]["weight_kg"] * i["quantity"] for i in known)
    longest = max(max(i["ship"]["package"]) for i in known)
    return round(weight, 1), int(longest)


def _item_label(item) -> str:
    size = f", {item['size']}" if item["size"] else ""
    length = f", {item['length']} м" if item["length"] else ""
    return f"{item['title']}{size}{length}, {item['quantity']} шт."


# --------------------------------------------------------------- checks ---


def _same_phone_orders(order):
    from order.models import Order

    digits = normalize_phone(order.phone)
    if not digits:
        return Order.objects.none()
    pattern = r"\D*".join(digits[-9:]) + r"\D*$"
    return Order.objects.exclude(pk=order.pk).filter(phone__regex=pattern)


def _shop_threshold() -> int:
    try:
        from project.free_shipping import get_shop_settings

        settings = get_shop_settings()
        if settings.free_shipping_enabled:
            return int(settings.free_shipping_threshold or 0)
    except Exception:
        pass
    return 0


def order_checks(order, items=None) -> list[str]:
    """Plain-text lines, each starting with ⚠️ (act) or ℹ️ (good to know)."""
    from order.models import Order

    lines: list[str] = []
    try:
        items = order_items(order) if items is None else items
        address = (order.address or "").lower()

        if order.payment_type == Order.PAYMENT_ROZETKA_UNPAID:
            lines.append("⚠️ Rozetka: ще не оплачено, не відправляти")
        if not order.phone:
            lines.append("⚠️ Немає телефону")
        elif not is_mobile(order.phone):
            lines.append("⚠️ Номер схожий на неправильний, перевірте його")

        parcel = _parcel(items)
        if parcel:
            weight, longest = parcel
            lines.append(f"📦 Посилка: ~{weight:g} кг, найдовша сторона ~{longest} см")
            if "поштомат" in address and (
                longest > POST_BOX_MAX_CM or weight > POST_BOX_MAX_KG
            ):
                lines.append(
                    "⚠️ Поштомат: килим туди не влізе. Запропонуйте відділення"
                )
            else:
                limit = _BRANCH_LIMIT_RE.search(address)
                if limit and weight > int(limit.group(1)):
                    lines.append(
                        f"⚠️ Відділення приймає до {limit.group(1)} кг, "
                        f"а посилка ~{weight:g} кг. Запропонуйте інше відділення"
                    )
                elif limit and longest > LIMITED_BRANCH_MAX_CM:
                    lines.append(
                        f"⚠️ Рулон ~{longest} см: у відділення «до {limit.group(1)} кг» "
                        "можуть не прийняти (там до ~120 см). Краще вантажне відділення"
                    )

        for item in items:
            if item["last"]:
                lines.append(
                    f"ℹ️ Останній на складі: {item['title']} {item['size']}. "
                    "Перевірте, що він є"
                )

        others = _same_phone_orders(order)
        day_ago = (order.created or timezone.now()) - timedelta(hours=24)
        recent = [
            o.order_number or o.pk
            for o in others.filter(created__gte=day_ago).exclude(
                status=Order.STATUS_CANCELLED
            )[:3]
        ]
        if recent:
            lines.append(
                "⚠️ З цього номера ще замовлення за добу: "
                + ", ".join(f"№{n}" for n in recent)
                + ". Можливо, дубль"
            )
        cancelled = others.filter(status=Order.STATUS_CANCELLED).count()
        if cancelled:
            lines.append(f"⚠️ Раніше з цього номера скасовано замовлень: {cancelled}")
        done = others.filter(
            status__in=(Order.STATUS_SHIPPED, Order.STATUS_COMPLETED)
        ).count()
        if done:
            lines.append(f"ℹ️ Вже купував у нас: {done} раз(и)")

        if order.payment_type == Order.PAYMENT_CASH:
            total = float(order.total_price or 0)
            if total >= BIG_COD_SUM:
                lines.append(
                    f"ℹ️ Оплата при отриманні на {total:.0f} грн. "
                    "Можна попросити передоплату 200 грн"
                )
            threshold = _shop_threshold()
            if (
                order.source == Order.SOURCE_SITE
                and not order.free_shipping
                and threshold
                and 0 < threshold - total <= FREE_SHIPPING_HINT_GAP
            ):
                lines.append(
                    f"ℹ️ До безкоштовної доставки не вистачило {threshold - total:.0f} грн"
                )
    except Exception:
        logger.exception("order checks failed for order %s", getattr(order, "pk", "?"))
    return lines


# ---------------------------------------------------------------- texts ---


def _delivery_text(order) -> str:
    try:
        from order.email_utils import delivery_parts

        city, branch = delivery_parts(order.city, order.address)
    except Exception:
        city, branch = order.city or "", order.address or ""
    branch = re.sub(r"\s*\([^)]*кг[^)]*\)", "", branch or "").strip()
    parts = [p for p in (city, branch) if p]
    return ", ".join(parts) if parts else ""


def _payment_text(order) -> str:
    from order.models import Order

    total = f"{float(order.total_price or 0):.0f} грн"
    if order.payment_type == Order.PAYMENT_CASH:
        return f"Сума: {total}, оплата при отриманні."
    if order.payment_type in (Order.PAYMENT_LIQPAY, Order.PAYMENT_ROZETKA):
        return f"Сума: {total}, вже оплачено."
    if order.payment_type == Order.PAYMENT_PREPAY:
        return f"Сума: {total}, передоплата на картку."
    return f"Сума: {total}."


def _shipping_text(order) -> str:
    if order.free_shipping:
        return "Доставка для вас безкоштовна."
    return "Доставку оплачуєте на пошті за тарифом Нової Пошти."


def customer_message(order, items=None) -> str:
    """Plain text for Viber / Telegram / SMS. Simple, warm, no em dashes."""
    items = order_items(order) if items is None else items
    name = (order.name or "").strip()
    hello = f"Добрий день, {name}!" if name else "Добрий день!"
    lines = [
        hello,
        "Це магазин килимів mr.Carpet (mrcarpet24.com).",
        f"Ми отримали ваше замовлення №{order.order_number or order.pk}:",
    ]
    lines += [f"• {_item_label(i)}" for i in items] or ["• (див. замовлення)"]
    lines.append(_payment_text(order))
    delivery = _delivery_text(order)
    if delivery:
        lines.append(f"Доставка: Нова Пошта, {delivery}.")
    lines.append(_shipping_text(order))
    lines.append("")
    lines.append(
        "Підтвердіть, будь ласка, що все вірно, і ми відправимо килим. "
        "Номер накладної надішлемо сюди."
    )
    lines.append("Дякуємо!")
    return "\n".join(lines)


def _say_size(size: str) -> str:
    match = re.match(r"(\d+)x(\d+)", size or "")
    if not match:
        return size
    a, b = (int(v) / 100 for v in match.groups())
    return f"{a:g} на {b:g} м".replace(".", ",")


def call_script(order, items=None, checks=None) -> str:
    """Plain text: what to say on the phone, step by step."""
    from order.models import Order

    items = order_items(order) if items is None else items
    checks = order_checks(order, items) if checks is None else checks
    name = (order.name or "").strip()
    goods = "; ".join(
        f"{i['title']}, розмір {_say_size(i['size'])}"
        + (f", {i['quantity']} шт." if i["quantity"] > 1 else "")
        for i in items
    ) or "товар із замовлення"
    total = f"{float(order.total_price or 0):.0f} грн"
    lines = [
        f"📞 {name or 'Покупець'}, {order.phone or 'телефон не вказано'}",
        "",
        f"1. «Добрий день{', ' + name if name else ''}! Це магазин килимів mr.Carpet. "
        "Ви оформили у нас замовлення. Зручно говорити хвилинку?»",
        f"2. «Ви замовили: {goods}. Все вірно?»",
    ]
    if order.payment_type == Order.PAYMENT_CASH:
        pay = f"3. «Сума {total}, оплата при отриманні на пошті."
    elif order.payment_type == Order.PAYMENT_ROZETKA_UNPAID:
        pay = f"3. «Сума {total}. Бачимо, що оплата на Розетці ще не пройшла. Підкажіть, будь ласка, коли зможете оплатити?"
    else:
        pay = f"3. «Сума {total}, оплату вже отримали, дякуємо."
    pay += (" Доставка для вас безкоштовна.»" if order.free_shipping
            else " Доставку Нова Пошта рахує окремо, за своїм тарифом.»")
    lines.append(pay)
    delivery = _delivery_text(order)
    lines.append(
        f"4. «Відправляємо на Нову Пошту: {delivery}. Правильно?»"
        if delivery
        else "4. «На яке відділення Нової Пошти відправити?» (адреси немає)"
    )
    lines.append(
        "5. «Відправимо найближчим часом, номер накладної надішлемо у Viber або SMS.»"
    )
    to_ask = [c for c in checks if c.startswith("⚠️") or "безкоштовної" in c]
    if to_ask:
        lines.append("")
        lines.append("Уточнити під час дзвінка:")
        lines.extend(to_ask)
        if any("безкоштовної" in c for c in to_ask):
            lines.append(
                "Можна сказати: «Якщо додасте ще щось на цю суму, доставка буде безкоштовна.»"
            )
    lines += [
        "",
        "6. «Дякуємо за замовлення! Гарного дня.»",
        "",
        "Не відповідає: надішліть текст кнопкою «✉️ Текст для месенджера».",
        "Передумав: змініть статус на «Скасовано» в адмінці.",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------- telegram ---


def order_keyboard(order) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✉️ Текст для месенджера", "callback_data": f"{CB_MESSAGE}:{order.pk}"},
                {"text": "📞 Сценарій дзвінка", "callback_data": f"{CB_CALL}:{order.pk}"},
            ]
        ]
    }


def viber_link_token(order) -> str:
    return signing.dumps(order.pk, salt=SIGN_SALT)


def order_from_viber_token(token: str):
    from order.models import Order

    try:
        pk = signing.loads(token, salt=SIGN_SALT, max_age=LINK_MAX_AGE)
    except signing.BadSignature:
        return None
    return Order.objects.filter(pk=pk).first()


def messenger_buttons(order) -> dict | None:
    digits = normalize_phone(order.phone)
    if not digits:
        return None
    base = getattr(django_settings, "SITE_URL", "https://mrcarpet24.com").rstrip("/")
    viber = f"{base}/api/order-viber/{viber_link_token(order)}/"
    return {
        "inline_keyboard": [
            [
                {"text": "Viber", "url": viber},
                {"text": "Telegram", "url": f"https://t.me/+{digits}"},
                {"text": "WhatsApp", "url": f"https://wa.me/{digits}"},
            ]
        ]
    }


def handle_order_callback(callback: dict) -> bool:
    """True when the callback is one of our order buttons (handled)."""
    data = callback.get("data") or ""
    action, _, raw_pk = data.partition(":")
    if action not in (CB_MESSAGE, CB_CALL):
        return False

    from order.models import Order
    from project.models import TelegramSettings
    from project.telegram_api import answer_callback_query, send_message

    cq_id = callback.get("id")
    message = callback.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    try:
        settings = TelegramSettings.load()
        if not chat_id or chat_id != str(settings.chat_id or "").strip():
            answer_callback_query(cq_id, "Чужий чат", show_alert=True)
            return True
        order = Order.objects.filter(pk=int(raw_pk or 0)).first()
        if order is None:
            answer_callback_query(cq_id, "Замовлення не знайдено", show_alert=True)
            return True
        items = order_items(order)
        if action == CB_MESSAGE:
            text = (
                "Скопіюйте і надішліть покупцю (натисніть на текст):\n"
                f"<pre>{_esc(customer_message(order, items))}</pre>"
            )
            markup = messenger_buttons(order)
        else:
            text = _esc(call_script(order, items))
            markup = None
        send_message(
            text,
            chat_id=chat_id,
            message_thread_id=message.get("message_thread_id"),
            reply_to_message_id=message.get("message_id"),
            reply_markup=markup,
            parse_mode="HTML",
        )
        answer_callback_query(cq_id)
    except Exception:
        logger.exception("order callback failed: %s", data)
        try:
            answer_callback_query(cq_id, "Помилка, спробуйте ще раз", show_alert=True)
        except Exception:
            pass
    return True
