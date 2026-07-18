"""Allowlist tools — LLM never gets ORM."""
from __future__ import annotations

from typing import Any

from django.db.models import Q

from catalog.models import Product, ProductAttribute
from order.models import Order

READ_TOOLS = {
    "count_orders",
    "list_recent_orders",
    "get_order",
    "count_products",
    "count_in_stock_products",
    "get_product_stock",
}

WRITE_TOOLS = {
    "set_order_status",
    "send_order_email",
    "change_stock_quantity",
}

ALLOWED_TOOLS = READ_TOOLS | WRITE_TOOLS

STATUS_CODES = {c[0] for c in Order.STATUS_CHOICES}
MAX_STOCK_QTY = 9999


def tool_specs_for_prompt() -> str:
    return """
READ tools (execute immediately):
- count_orders(status?: string) — count orders; status one of: new, awaiting_payment, paid, shipped, completed, cancelled
- list_recent_orders(limit?: int<=10, status?: string)
- get_order(order_number: int|string)
- count_products()
- count_in_stock_products()
- get_product_stock(query: string) — search product by title/slug/url

WRITE tools (NEVER execute yourself — system will ask human confirm):
- set_order_status(order_number, status)
- send_order_email(order_number, subject, body)
- change_stock_quantity(url?: string, query?: string, size?: string, mode: "set"|"delta", value: int)
  Example set 5: mode=set value=5; add 2: mode=delta value=2; remove 1: mode=delta value=-1
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

    return {"ok": False, "error": "unhandled"}


def validate_write_args(name: str, args: dict | None) -> tuple[bool, str, dict]:
    args = dict(args or {})
    if name not in WRITE_TOOLS:
        return False, f"unknown write tool: {name}", {}

    if name == "set_order_status":
        number = args.get("order_number")
        status = (args.get("status") or "").strip()
        if number is None:
            return False, "order_number required", {}
        try:
            number = int(str(number).strip())
        except ValueError:
            return False, "order_number must be integer", {}
        if status not in STATUS_CODES:
            return False, f"invalid status: {status}", {}
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
        from project.smtp_utils import send_smtp_mail

        ok = send_smtp_mail(
            args["subject"],
            args["body"],
            [args["email"]],
            fail_silently=True,
        )
        return {
            "ok": bool(ok),
            "email": args["email"],
            "order_number": args["order_number"],
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
    if name == "set_order_status":
        label = dict(Order.STATUS_CHOICES).get(args["status"], args["status"])
        return (
            f"Змінити статус замовлення №{args['order_number']} → {label} ({args['status']})"
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
