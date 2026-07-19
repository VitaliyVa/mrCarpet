"""GA4 Measurement Protocol — server-side purchase (cash + LiqPay paid)."""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)

MP_COLLECT = "https://www.google-analytics.com/mp/collect"
MP_DEBUG = "https://www.google-analytics.com/debug/mp/collect"
MP_TIMEOUT = 8


def _measurement_id() -> str:
    return (getattr(settings, "GA4_MEASUREMENT_ID", "") or "").strip()


def _api_secret() -> str:
    return (getattr(settings, "GA4_API_SECRET", "") or "").strip()


def mp_configured() -> bool:
    return bool(_measurement_id() and _api_secret())


def client_id_from_ga_cookie(cookie_value: str | None) -> str | None:
    """Parse _ga=GA1.1.XXXXXXXXXX.YYYYYYYYYY → XXXXXXXXXX.YYYYYYYYYY."""
    if not cookie_value:
        return None
    parts = str(cookie_value).strip().split(".")
    if len(parts) >= 4 and parts[-2].isdigit() and parts[-1].isdigit():
        return f"{parts[-2]}.{parts[-1]}"
    return None


def client_id_for_order(order, request=None) -> str:
    if request is not None:
        cid = client_id_from_ga_cookie(request.COOKIES.get("_ga"))
        if cid:
            return cid
    seed = f"mrcarpet-order:{getattr(order, 'order_number', None) or order.pk}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{int(digest[:8], 16)}.{int(digest[8:16], 16)}"


def _mp_payload_from_purchase(purchase: dict, client_id: str) -> dict:
    params: dict[str, Any] = {
        "currency": purchase.get("currency") or "UAH",
        "transaction_id": str(purchase.get("transaction_id") or ""),
        "value": float(purchase.get("value") or 0),
        "engagement_time_msec": 1,
        "session_id": str(purchase.get("transaction_id") or "")[-10:],
    }
    if purchase.get("shipping") is not None:
        params["shipping"] = float(purchase["shipping"] or 0)
    if purchase.get("payment_type"):
        params["payment_type"] = purchase["payment_type"]
    items = []
    for it in purchase.get("items") or []:
        items.append(
            {
                "item_id": str(it.get("item_id") or ""),
                "item_name": it.get("item_name") or "",
                "item_brand": it.get("item_brand") or "mr.Carpet",
                "item_category": it.get("item_category") or "",
                "item_variant": it.get("item_variant") or "",
                "price": float(it.get("price") or 0),
                "quantity": int(it.get("quantity") or 1),
                "index": int(it.get("index") or 0),
            }
        )
    if items:
        params["items"] = items
    return {
        "client_id": client_id,
        "events": [{"name": "purchase", "params": params}],
    }


def send_mp_purchase(
    purchase: dict,
    *,
    client_id: str,
    debug: bool = False,
) -> bool:
    """POST purchase to MP. Returns True on HTTP 2xx (debug also checks validation)."""
    if not mp_configured():
        logger.info("[ga4-mp] skip: GA4_MEASUREMENT_ID / GA4_API_SECRET not set")
        return False
    tid = str(purchase.get("transaction_id") or "")
    if not tid:
        logger.warning("[ga4-mp] skip: empty transaction_id")
        return False

    qs = urlencode(
        {"measurement_id": _measurement_id(), "api_secret": _api_secret()}
    )
    url = f"{MP_DEBUG if debug else MP_COLLECT}?{qs}"
    body = _mp_payload_from_purchase(purchase, client_id)
    try:
        resp = requests.post(url, json=body, timeout=MP_TIMEOUT)
        if debug:
            data = resp.json() if resp.content else {}
            msgs = data.get("validationMessages") or []
            if msgs:
                logger.warning("[ga4-mp] validation: %s", msgs)
                print(f"[ga4-mp] validation FAILED: {msgs}")
                return False
            print(f"[ga4-mp] validation OK tx={tid}")
            return True
        if 200 <= resp.status_code < 300:
            print(f"[ga4-mp] purchase sent tx={tid} status={resp.status_code}")
            return True
        logger.warning(
            "[ga4-mp] HTTP %s body=%s", resp.status_code, (resp.text or "")[:300]
        )
        print(f"[ga4-mp] FAILED HTTP {resp.status_code}")
        return False
    except Exception as exc:
        logger.exception("[ga4-mp] send failed: %s", exc)
        print(f"[ga4-mp] FAILED: {exc}")
        return False


def send_order_purchase_mp(order, request=None, *, force: bool = False) -> bool:
    """Build payload from order.cart and send once (dedupe via ga4_mp_sent)."""
    if not mp_configured():
        return False
    if getattr(order, "ga4_mp_sent", False) and not force:
        return False

    from project.ga4_ecommerce import order_allows_purchase_event, purchase_payload

    if not order_allows_purchase_event(order) and not force:
        return False

    cart = getattr(order, "cart", None)
    if cart is None:
        return False

    try:
        purchase = purchase_payload(order, cart)
    except Exception as exc:
        logger.exception("[ga4-mp] payload failed: %s", exc)
        return False

    client_id = client_id_for_order(order, request=request)
    ok = send_mp_purchase(purchase, client_id=client_id, debug=False)
    if ok and hasattr(order, "ga4_mp_sent"):
        try:
            type(order).objects.filter(pk=order.pk, ga4_mp_sent=False).update(
                ga4_mp_sent=True
            )
        except Exception:
            logger.exception("[ga4-mp] failed to mark ga4_mp_sent")
    return ok


def enqueue_order_purchase_mp(order_id: int, client_id: str | None = None) -> None:
    """Fire MP purchase after DB commit (non-blocking)."""

    def _after_commit():
        close_old_connections()
        try:
            from order.models import Order

            order = (
                Order.objects.select_related("cart")
                .filter(pk=order_id)
                .first()
            )
            if not order:
                return

            class _Req:
                COOKIES = {"_ga": f"GA1.1.{client_id}"} if client_id else {}

            req = _Req() if client_id else None
            send_order_purchase_mp(order, request=req)
        except Exception as exc:
            logger.exception("[ga4-mp] enqueue failed: %s", exc)
            print(f"[ga4-mp] enqueue FAILED: {exc}")
        finally:
            close_old_connections()

    def _run():
        try:
            _after_commit()
        except Exception:
            logger.exception("[ga4-mp] thread failed")

    def _schedule():
        threading.Thread(target=_run, daemon=True).start()

    transaction.on_commit(_schedule)
