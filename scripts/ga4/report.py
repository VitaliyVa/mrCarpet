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


def main() -> None:
    parser = argparse.ArgumentParser(description="GA4 quick reports")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--realtime", action="store_true")
    args = parser.parse_args()
    ensure_credentials()
    if args.realtime:
        run_realtime()
    else:
        run_overview(args.days)


if __name__ == "__main__":
    main()
