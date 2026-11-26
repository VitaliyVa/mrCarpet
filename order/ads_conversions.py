"""Paid orders as Google Ads offline click conversions (CSV upload).

Ads learns best from money that really came in. GA4 imports cannot take a
sale back, so a cash parcel nobody picks up stays a "conversion" forever.
This export lists only real sales (card: paid or later; cash: paid or
completed) that carry an ad click id, in the Google Ads click-conversion
upload format. Upload it in Ads > Goals > Conversions > Uploads, or point a
scheduled upload at the file `manage.py export_ads_conversions` writes.

Conversion time:
  * card: the LiqPay payment time (the order time if the payment row is gone);
  * cash: the moment the order became completed, or its last change when the
    manager set "paid" without completing it.
Times are written in UTC with an explicit +0000 offset.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone

from order.models import Order
from project.ga4_ecommerce import COD_DELIVERED_STATUSES, PREPAID_SALE_STATUSES, order_is_real_sale

DEFAULT_CONVERSION_NAME = "Оплачене замовлення"
# Google Ads accepts clicks up to 90 days old.
CLICK_MAX_AGE_DAYS = 90

HEADER = [
    "Google Click ID",
    "Conversion Name",
    "Conversion Time",
    "Conversion Value",
    "Conversion Currency",
    "Order ID",
]
BRAID_HEADER = ["GBRAID", "WBRAID"]


def _fmt_time(value: datetime) -> str:
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt_timezone.utc)
    return value.astimezone(dt_timezone.utc).strftime("%Y-%m-%d %H:%M:%S+0000")


def conversion_time(order) -> datetime | None:
    if order.payment_type == Order.PAYMENT_CASH:
        if order.status == Order.STATUS_COMPLETED and order.completed_at:
            return order.completed_at
        return order.updated or order.created
    try:
        payment = order.payment
    except Exception:  # RelatedObjectDoesNotExist: no LiqPay row
        payment = None
    stamp = getattr(payment, "timestamp", None)
    return stamp or order.created


def candidate_orders(queryset=None):
    """Real-sale orders with a click id (DB-side prefilter)."""
    qs = Order.objects.all() if queryset is None else queryset
    from django.db.models import Q

    # Marketplace orders carry no ad click of ours and must never be uploaded.
    qs = qs.filter(source=Order.SOURCE_SITE)

    sale = Q(payment_type=Order.PAYMENT_CASH, status__in=COD_DELIVERED_STATUSES) | (
        ~Q(payment_type=Order.PAYMENT_CASH) & Q(status__in=PREPAID_SALE_STATUSES)
    )
    has_click = ~Q(gclid="") | ~Q(gbraid="") | ~Q(wbraid="")
    return qs.filter(sale).filter(has_click).select_related("payment").order_by("created")


def conversion_rows(
    queryset=None,
    *,
    conversion_name: str = DEFAULT_CONVERSION_NAME,
    since: datetime | None = None,
    with_braid: bool = False,
) -> list[list[str]]:
    """Rows for the upload file (without the header).

    gclid wins when an order carries several ids (Ads wants exactly one).
    Orders with only gbraid/wbraid are included only when `with_braid`.
    """
    now = timezone.now()
    oldest_click = now - timedelta(days=CLICK_MAX_AGE_DAYS)
    rows = []
    for order in candidate_orders(queryset):
        if not order_is_real_sale(order):
            continue
        when = conversion_time(order)
        if when is None or (since is not None and when < since):
            continue
        if order.ad_click_at:
            if order.ad_click_at < oldest_click or when < order.ad_click_at:
                continue
        gclid, gbraid, wbraid = order.gclid, "", ""
        if not gclid:
            if not with_braid:
                continue
            gbraid = order.gbraid
            wbraid = "" if gbraid else order.wbraid
        value = f"{float(order.total_price or 0):.2f}"
        row = [
            gclid,
            conversion_name,
            _fmt_time(when),
            value,
            "UAH",
            str(order.order_number or order.pk),
        ]
        if with_braid:
            row += [gbraid, wbraid]
        rows.append(row)
    return rows


def write_csv(fp, rows, *, with_braid: bool = False) -> None:
    writer = csv.writer(fp, lineterminator="\n")
    writer.writerow(HEADER + (BRAID_HEADER if with_braid else []))
    writer.writerows(rows)
