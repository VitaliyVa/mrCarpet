#!/usr/bin/env python3
"""Quick GA4 reports for Cursor / terminal (REST)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _auth import api_json  # noqa: E402
from _env import ensure_credentials, property_id  # noqa: E402


def run_overview(days: int) -> None:
    pid = property_id()
    start = f"{days}daysAgo"
    base = f"https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"

    overview = api_json(
        "POST",
        base,
        payload={
            "dateRanges": [{"startDate": start, "endDate": "today"}],
            "metrics": [
                {"name": "activeUsers"},
                {"name": "sessions"},
                {"name": "screenPageViews"},
                {"name": "engagedSessions"},
            ],
        },
    )
    print(f"=== Overview last {days}d ===")
    rows = overview.get("rows") or []
    if rows:
        labels = ["activeUsers", "sessions", "pageViews", "engagedSessions"]
        for label, cell in zip(labels, rows[0].get("metricValues", [])):
            print(f"  {label}: {cell.get('value')}")
    else:
        print("  (no rows yet — new property / no traffic in range)")

    pages = api_json(
        "POST",
        base,
        payload={
            "dateRanges": [{"startDate": start, "endDate": "today"}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}],
            "limit": "15",
        },
    )
    print("\n=== Top pages ===")
    for row in pages.get("rows") or []:
        path = row["dimensionValues"][0]["value"]
        views = row["metricValues"][0]["value"]
        users = row["metricValues"][1]["value"]
        print(f"  {views:>6} views | {users:>4} users | {path}")

    events = api_json(
        "POST",
        base,
        payload={
            "dateRanges": [{"startDate": start, "endDate": "today"}],
            "dimensions": [{"name": "eventName"}],
            "metrics": [{"name": "eventCount"}],
            "limit": "20",
        },
    )
    print("\n=== Events ===")
    for row in events.get("rows") or []:
        print(f"  {row['metricValues'][0]['value']:>6} | {row['dimensionValues'][0]['value']}")


def run_realtime() -> None:
    pid = property_id()
    resp = api_json(
        "POST",
        f"https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runRealtimeReport",
        payload={
            "dimensions": [{"name": "unifiedScreenName"}],
            "metrics": [{"name": "activeUsers"}],
            "limit": "10",
        },
    )
    print("=== Realtime (approx last 30m) ===")
    rows = resp.get("rows") or []
    total = sum(int(r["metricValues"][0]["value"]) for r in rows)
    print(f"  activeUsers (sum of rows): {total}")
    for row in rows:
        title = row["dimensionValues"][0]["value"]
        print(f"  {row['metricValues'][0]['value']} | {title.encode('utf-8', 'replace').decode('utf-8')}")


FUNNEL_EVENTS = (
    "view_item",
    "add_to_cart",
    "view_cart",
    "begin_checkout",
    "add_shipping_info",
    "add_payment_info",
    "purchase",
)


def run_ecommerce(days: int) -> None:
    """Ecommerce funnel counts + purchase revenue (if available)."""
    pid = property_id()
    start = f"{days}daysAgo"
    base = f"https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"

    events = api_json(
        "POST",
        base,
        payload={
            "dateRanges": [{"startDate": start, "endDate": "today"}],
            "dimensions": [{"name": "eventName"}],
            "metrics": [{"name": "eventCount"}, {"name": "totalUsers"}],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "eventName",
                    "inListFilter": {"values": list(FUNNEL_EVENTS)},
                }
            },
            "limit": "50",
        },
    )
    by_name: dict[str, tuple[str, str]] = {}
    for row in events.get("rows") or []:
        name = row["dimensionValues"][0]["value"]
        count = row["metricValues"][0]["value"]
        users = row["metricValues"][1]["value"]
        by_name[name] = (count, users)

    print(f"=== Ecommerce funnel last {days}d ===")
    for name in FUNNEL_EVENTS:
        count, users = by_name.get(name, ("0", "0"))
        print(f"  {name:22} events={count:>6}  users={users:>5}")

    try:
        rev = api_json(
            "POST",
            base,
            payload={
                "dateRanges": [{"startDate": start, "endDate": "today"}],
                "metrics": [
                    {"name": "purchaseRevenue"},
                    {"name": "ecommercePurchases"},
                    {"name": "averagePurchaseRevenue"},
                ],
            },
        )
        rows = rev.get("rows") or []
        if rows:
            m = rows[0].get("metricValues") or []
            print("\n=== Purchase revenue ===")
            labels = ["purchaseRevenue", "ecommercePurchases", "avgPurchaseRevenue"]
            for label, cell in zip(labels, m):
                print(f"  {label}: {cell.get('value')}")
    except Exception as exc:
        print(f"\n(revenue metrics unavailable: {exc})")

    try:
        src = api_json(
            "POST",
            base,
            payload={
                "dateRanges": [{"startDate": start, "endDate": "today"}],
                "dimensions": [
                    {"name": "sessionSource"},
                    {"name": "sessionMedium"},
                ],
                "metrics": [{"name": "sessions"}, {"name": "ecommercePurchases"}],
                "limit": "15",
                "orderBys": [
                    {"metric": {"metricName": "sessions"}, "desc": True}
                ],
            },
        )
        print("\n=== Top session source / medium ===")
        for row in src.get("rows") or []:
            s = row["dimensionValues"][0]["value"]
            m = row["dimensionValues"][1]["value"]
            sessions = row["metricValues"][0]["value"]
            purchases = row["metricValues"][1]["value"]
            print(f"  {sessions:>6} sess | {purchases:>4} purch | {s} / {m}")
    except Exception as exc:
        print(f"\n(source/medium unavailable: {exc})")


def main() -> None:
    parser = argparse.ArgumentParser(description="GA4 quick reports")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument(
        "--ecommerce",
        action="store_true",
        help="Ecommerce funnel + revenue + source/medium",
    )
    args = parser.parse_args()
    ensure_credentials()
    if args.realtime:
        run_realtime()
    elif args.ecommerce:
        run_ecommerce(args.days)
    else:
        run_overview(args.days)


if __name__ == "__main__":
    main()
