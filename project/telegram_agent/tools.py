"""Allowlist tools — LLM never gets ORM."""
from __future__ import annotations

import base64
import re
import time
from typing import Any

from django.db.models import Q

from catalog.models import Product, ProductAttribute
from order.models import Order

from .status_labels import STATUS_CODES, STATUS_LABEL_BY_CODE, normalize_status

READ_TOOLS = {
    "count_orders",
    "list_recent_orders",
    "get_order",
    "find_orders",
    "count_products",
    "count_in_stock_products",
    "get_product_stock",
    "get_ga4_report",
}

ANALYTICS_COOLDOWN_SEC = 60
_analytics_cooldown: dict[str, float] = {}

WRITE_TOOLS = {
    "set_order_status",
    "send_order_email",
    "change_stock_quantity",
}

BATCH_TOOL = "batch"
ALLOWED_TOOLS = READ_TOOLS | WRITE_TOOLS

MAX_STOCK_QTY = 9999


def tool_specs_for_prompt() -> str:
    status_lines = ", ".join(
        f"{label} ({code})" for code, label in Order.STATUS_CHOICES
    )
    return f"""
READ tools (execute immediately):
- count_orders(status?: string) — status codes: {status_lines}
- list_recent_orders(limit?: int<=10, status?: string)
- get_order(order_number: int|string)
- find_orders(phone?: string, query?: string, status?: string, limit?: int<=10)
  — пошук за телефоном / ім'ям / містом
- count_products()
- count_in_stock_products()
- get_product_stock(query: string) — search product by title/slug/url
- get_ga4_report(days?: int 1..30, report?: dashboard|ecommerce|realtime)
  — GA4 analytics with chart images (Ukrainian shop metrics)

WRITE tools (NEVER execute yourself — system will ask human confirm):
- set_order_status(order_number, status) — status = code (completed) або UA (Виконано)
- send_order_email(order_number, subject, body) — subject/body УКРАЇНСЬКОЮ
- change_stock_quantity(url?: string, query?: string, size?: string, mode: "set"|"delta", value: int)
  Example set 5: mode=set value=5; add 2: mode=delta value=2; remove 1: mode=delta value=-1

Якщо користувач просить КІЛЬКА write-дій (напр. статус + лист) —
поверни type=tools з УСІМА write calls в одному JSON (не тільки першу).
Номер замовлення бери з USER / HISTORY / REPLY_CONTEXT, не вигадуй.
Не плутай change_stock_quantity зі зміною статусу замовлення.
У type=reply людям пиши статуси УКРАЇНСЬКОЮ (код у дужках ок).
""".strip()


def _order_brief(order: Order) -> dict[str, Any]:
    return {
        "order_number": order.order_number,
        "status": order.status,
        "status_label": order.get_status_display(),
        "customer": f"{order.name} {order.surname}".strip(),
        "phone": order.phone or "",
        "email": order.email or "",
        "city": order.city or "",
        "total_price": order.total_price,
        "payment_type": order.payment_type,
        "created": order.created.isoformat() if order.created else None,
    }


def execute_read_tool(name: str, args: dict | None) -> dict[str, Any]:
    args = args or {}
    if name not in READ_TOOLS:
        return {"ok": False, "error": f"unknown read tool: {name}"}

    if name == "count_orders":
        qs = Order.objects.all()
        status = (args.get("status") or "").strip()
        if status:
            if status not in STATUS_CODES:
                return {"ok": False, "error": f"invalid status: {status}"}
            qs = qs.filter(status=status)
        return {"ok": True, "count": qs.count(), "status": status or None}

    if name == "list_recent_orders":
        try:
            limit = int(args.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 10))
        qs = Order.objects.all().order_by("-created")
        status = (args.get("status") or "").strip()
        if status:
            if status not in STATUS_CODES:
                return {"ok": False, "error": f"invalid status: {status}"}
            qs = qs.filter(status=status)
        return {"ok": True, "orders": [_order_brief(o) for o in qs[:limit]]}

    if name == "get_order":
        number = args.get("order_number")
        if number is None:
            return {"ok": False, "error": "order_number required"}
        try:
            number = int(str(number).strip())
        except ValueError:
            return {"ok": False, "error": "order_number must be integer"}
        order = Order.objects.filter(order_number=number).first()
        if not order:
            return {"ok": False, "error": "order not found"}
        brief = _order_brief(order)
        items = []
        try:
            for cp in order.cart.cart_products.select_related(
                "product_attr__product", "product_attr__size"
            ):
                items.append(
                    {
                        "title": cp.product_attr.product.title,
                        "size": str(cp.product_attr.size) if cp.product_attr.size else "",
                        "qty": cp.quantity,
                    }
                )
        except Exception:
            pass
        brief["items"] = items
        return {"ok": True, "order": brief}

    if name == "find_orders":
        phone = re.sub(r"\D+", "", str(args.get("phone") or ""))
        query = (args.get("query") or "").strip()
        status = (args.get("status") or "").strip()
        try:
            limit = int(args.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 10))
        qs = Order.objects.all().order_by("-created")
        if status:
            status = normalize_status(status) or status
            if status not in STATUS_CODES:
                return {"ok": False, "error": f"invalid status: {status}"}
            qs = qs.filter(status=status)
        if phone:
            # match last 9–10 digits (UA mobiles vary in formatting)
            tail = phone[-9:] if len(phone) >= 9 else phone
            qs = qs.filter(phone__icontains=tail)
        elif query:
            qs = qs.filter(
                Q(name__icontains=query)
                | Q(surname__icontains=query)
                | Q(city__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )
        else:
            return {"ok": False, "error": "phone or query required"}
        orders = [_order_brief(o) for o in qs[:limit]]
        return {"ok": True, "found": len(orders), "orders": orders}

    if name == "count_products":
        return {"ok": True, "count": Product.admin_objects.count()}

    if name == "count_in_stock_products":
        # products with at least one attr qty > 0
        ids = (
            ProductAttribute.objects.filter(quantity__gt=0)
            .values_list("product_id", flat=True)
            .distinct()
        )
        return {"ok": True, "count": len(list(ids))}

    if name == "get_product_stock":
        query = (args.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "query required"}
        from .product_resolve import extract_slug_from_text, find_product

        products = []
        by_slug = find_product(query=query, url=query)
        if by_slug:
            products = [by_slug]
        else:
            slug = extract_slug_from_text(query)
            q = query
            if slug:
                q = slug
            products = list(
                Product.admin_objects.filter(
                    Q(title__icontains=q) | Q(slug__icontains=q)
                )
                .prefetch_related("product_attr__size")[:5]
            )
        result = []
        for p in products:
            attrs = []
            for a in p.product_attr.all():
                attrs.append(
                    {
                        "size": str(a.size) if a.size else "",
                        "quantity": a.quantity,
                        "in_stock": a.in_stock,
                    }
                )
            total = sum(a.quantity or 0 for a in p.product_attr.all())
            result.append(
                {
                    "id": p.pk,
                    "title": p.title,
                    "slug": p.slug,
                    "total_quantity": total,
                    "sizes": attrs,
                }
            )
        return {"ok": True, "products": result, "found": len(result)}

    if name == "get_ga4_report":
        return _execute_ga4_report(args)

    return {"ok": False, "error": "unhandled"}


def _execute_ga4_report(args: dict) -> dict[str, Any]:
    from project.ga4_charts import (
        build_caption,
        build_dashboard_photos,
        build_realtime_caption,
        render_funnel_chart,
        render_realtime_chart,
        render_revenue_chart,
        render_sources_chart,
    )
    from project.ga4_client import (
        Ga4ClientError,
        fetch_dashboard,
        fetch_ecommerce,
        fetch_realtime,
        ga4_configured,
    )

    chat_key = str(args.get("_chat_id") or "global")
    now = time.time()
    last = _analytics_cooldown.get(chat_key) or 0
    wait = ANALYTICS_COOLDOWN_SEC - (now - last)
    if wait > 0:
        return {
            "ok": False,
            "error": f"Зачекай {int(wait)} с перед наступним звітом GA4",
            "cooldown": True,
        }

    if not ga4_configured():
        return {
            "ok": False,
            "error": (
                "GA4 не налаштовано на сервері "
                "(GA4_PROPERTY_ID + GA4_SERVICE_ACCOUNT_JSON)."
            ),
        }

    try:
        days = int(args.get("days") or 7)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, 30))
    report = (args.get("report") or "dashboard").strip().lower()
    if report not in ("dashboard", "ecommerce", "realtime"):
        report = "dashboard"

    try:
        if report == "realtime":
            data = fetch_realtime()
            photos_raw = [("realtime.png", render_realtime_chart(data))]
            caption = build_realtime_caption(data)
            summary = {"active_users": data.get("active_users"), "screens": data.get("screens")}
        elif report == "ecommerce":
            data = fetch_ecommerce(days)
            dash = {
                "days": days,
                "funnel": data.get("funnel"),
                "sources": data.get("sources"),
                "kpis": {},
                "revenue": data.get("revenue"),
                "top_pages": [],
                "daily": [],
            }
            photos_raw = [
                ("01_funnel.png", render_funnel_chart(dash["funnel"] or [], days=days)),
                ("02_sources.png", render_sources_chart(dash["sources"] or [], days=days)),
                (
                    "03_sales.png",
                    render_revenue_chart(
                        dash.get("revenue") or {},
                        dash.get("funnel") or [],
                        days=days,
                    ),
                ),
            ]
            caption = build_caption(dash)
            summary = {
                "days": days,
                "revenue": data.get("revenue"),
                "funnel": data.get("funnel"),
            }
        else:
            data = fetch_dashboard(days)
            photos_raw = build_dashboard_photos(data)
            caption = build_caption(data)
            summary = {
                "days": days,
                "kpis": data.get("kpis"),
                "revenue": data.get("revenue"),
            }
    except Ga4ClientError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Помилка звіту GA4: {exc}"}

    _analytics_cooldown[chat_key] = time.time()
    photos = [
        {
            "name": fname,
            "b64": base64.b64encode(blob).decode("ascii"),
        }
        for fname, blob in photos_raw
        if blob
    ]
    return {
        "ok": True,
        "report": report,
        "days": days,
        "caption": caption,
        "summary": summary,
        "photos": photos,
        "skip_llm": True,
    }


def strip_tool_result_for_memory(result: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky photo payloads from chat memory."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    if "photos" in out:
        out["photos"] = f"[{len(result.get('photos') or [])} images]"
    return out


def validate_write_args(name: str, args: dict | None) -> tuple[bool, str, dict]:
    args = dict(args or {})
    if name not in WRITE_TOOLS:
        return False, f"unknown write tool: {name}", {}

    if name == "set_order_status":
        number = args.get("order_number")
        status_raw = (args.get("status") or "").strip()
        status = normalize_status(status_raw) or status_raw
        if number is None:
            return False, "order_number required", {}
        try:
            number = int(str(number).strip())
        except ValueError:
            return False, "order_number must be integer", {}
        if status not in STATUS_CODES:
            return False, f"invalid status: {status_raw}", {}
        if not Order.objects.filter(order_number=number).exists():
            return False, "order not found", {}
        return True, "", {"order_number": number, "status": status}

    if name == "send_order_email":
        number = args.get("order_number")
        subject = (args.get("subject") or "").strip()
        body = (args.get("body") or "").strip()
        if number is None:
            return False, "order_number required", {}
        try:
            number = int(str(number).strip())
        except ValueError:
            return False, "order_number must be integer", {}
        if not subject or not body:
            return False, "subject and body required", {}
        order = Order.objects.filter(order_number=number).first()
        if not order:
            return False, "order not found", {}
        if not order.email or order.email.endswith("@temp.com"):
            return False, "order has no real email", {}
        return True, "", {
            "order_number": number,
            "subject": subject[:200],
            "body": body[:4000],
            "email": order.email,
        }

    if name == "change_stock_quantity":
        from .product_resolve import find_product, find_product_attr

        mode = (args.get("mode") or "set").strip().lower()
        if mode not in ("set", "delta"):
            return False, "mode must be set|delta", {}
        try:
            value = int(args.get("value"))
        except (TypeError, ValueError):
            return False, "value must be int", {}
        url = (args.get("url") or "").strip()
        query = (args.get("query") or "").strip()
        size = (args.get("size") or "").strip() or None
        product = find_product(query=query or url, url=url)
        if not product:
            return False, "product not found", {}
        attr = find_product_attr(product, size)
        if not attr:
            return False, f"size not found for product ({size or 'default'})", {}
        old_qty = int(attr.quantity or 0)
        if mode == "set":
            new_qty = value
        else:
            new_qty = old_qty + value
        if new_qty < 0:
            return False, f"quantity would be negative ({old_qty} + delta)", {}
        if new_qty > MAX_STOCK_QTY:
            return False, f"quantity too large (max {MAX_STOCK_QTY})", {}
        size_label = str(attr.size) if attr.size else "—"
        return True, "", {
            "product_attr_id": attr.pk,
            "product_id": product.pk,
            "product_title": product.title,
            "size_label": size_label,
            "mode": mode,
            "value": value,
            "old_quantity": old_qty,
            "new_quantity": new_qty,
        }

    return False, "unhandled", {}


def execute_write_tool(name: str, args: dict) -> dict[str, Any]:
    if name == "set_order_status":
        order = Order.objects.get(order_number=args["order_number"])
        order.status = args["status"]
        order.save(update_fields=["status"])
        return {
            "ok": True,
            "order_number": order.order_number,
            "status": order.status,
            "status_label": order.get_status_display(),
        }

    if name == "send_order_email":
        from project.email_branding import wrap_plain_email
        from project.smtp_utils import send_smtp_mail

        plain, html = wrap_plain_email(
            args["body"],
            title=args["subject"],
            eyebrow=f"Замовлення №{args['order_number']}",
            preheader=args["subject"],
        )
        try:
            ok = send_smtp_mail(
                args["subject"],
                plain,
                [args["email"]],
                fail_silently=False,
                html_message=html,
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc)[:300],
                "email": args["email"],
                "order_number": args["order_number"],
            }
        return {
            "ok": bool(ok),
            "email": args["email"],
            "order_number": args["order_number"],
            **({} if ok else {"error": "SMTP send returned false"}),
        }

    if name == "change_stock_quantity":
        attr = ProductAttribute.objects.select_related("product", "size").get(
            pk=args["product_attr_id"]
        )
        attr.quantity = int(args["new_quantity"])
        attr.save(update_fields=["quantity"])
        return {
            "ok": True,
            "product": attr.product.title,
            "size": str(attr.size) if attr.size else "—",
            "old_quantity": args["old_quantity"],
            "new_quantity": attr.quantity,
        }

    return {"ok": False, "error": "unknown write tool"}


def describe_write(name: str, args: dict) -> str:
    if name == BATCH_TOOL:
        steps = args.get("steps") or []
        parts = [f"Пакетна дія ({len(steps)}):"]
        for i, step in enumerate(steps, 1):
            parts.append(f"{i}) {describe_write(step['name'], step['args'])}")
        return "\n".join(parts)
    if name == "set_order_status":
        label = STATUS_LABEL_BY_CODE.get(args["status"], args["status"])
        return (
            f"Змінити статус замовлення №{args['order_number']} → {label}"
        )
    if name == "send_order_email":
        return (
            f"Надіслати лист на {args.get('email')} "
            f"(замовлення №{args['order_number']})\n"
            f"Тема: {args['subject']}\n"
            f"Текст:\n{args['body'][:500]}"
        )
    if name == "change_stock_quantity":
        return (
            f"Змінити залишок на складі\n"
            f"Товар: {args['product_title']}\n"
            f"Розмір: {args['size_label']}\n"
            f"{args['old_quantity']} → {args['new_quantity']} шт"
        )
    return f"{name}: {args}"


def validate_write_calls(calls: list[dict]) -> tuple[bool, str, list[dict]]:
    """Validate a list of WRITE tool calls for a batch pending action."""
    clean_steps = []
    for call in calls:
        name = (call.get("name") or "").strip()
        args = call.get("args") or {}
        if name not in WRITE_TOOLS:
            return False, f"unknown write tool: {name}", []
        ok, err, clean = validate_write_args(name, args)
        if not ok:
            return False, f"{name}: {err}", []
        clean_steps.append({"name": name, "args": clean})
    if not clean_steps:
        return False, "empty write batch", []
    return True, "", clean_steps


def execute_write_calls(steps: list[dict]) -> dict:
    results = []
    all_ok = True
    for step in steps:
        result = execute_write_tool(step["name"], step["args"])
        step_ok = bool(result.get("ok"))
        if not step_ok:
            all_ok = False
        results.append(
            {
                "name": step["name"],
                "ok": step_ok,
                "result": result,
            }
        )
    return {"ok": all_ok, "steps": results}


def format_write_result_ua(name: str, result: dict) -> str:
    """Human-readable UA summary after confirm (for chat edit + memory)."""
    if name == BATCH_TOOL:
        lines = []
        for step in result.get("steps") or []:
            mark = "✅" if step.get("ok") else "❌"
            lines.append(
                f"{mark} {format_write_result_ua(step['name'], step.get('result') or {})}"
            )
        header = "✅ Усі кроки виконано" if result.get("ok") else "⚠️ Виконано частково"
        return header + "\n" + "\n".join(lines)

    if not result.get("ok"):
        err = result.get("error") or "помилка"
        return f"Не вдалося ({name}): {err}"

    if name == "set_order_status":
        label = result.get("status_label") or STATUS_LABEL_BY_CODE.get(
            result.get("status"), result.get("status")
        )
        return f"Статус №{result.get('order_number')} → {label}"
    if name == "send_order_email":
        return (
            f"Лист надіслано на {result.get('email')} "
            f"(замовлення №{result.get('order_number')})"
        )
    if name == "change_stock_quantity":
        return (
            f"Склад: {result.get('product')} ({result.get('size')}) "
            f"{result.get('old_quantity')} → {result.get('new_quantity')} шт"
        )
    return str(result)[:500]
