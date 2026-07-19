#!/usr/bin/env python3
"""GA4 Admin REST helpers (read/edit property config)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _auth import api_json  # noqa: E402
from _env import ensure_credentials, property_id  # noqa: E402

ADMIN = "https://analyticsadmin.googleapis.com/v1beta"


def cmd_info(_: argparse.Namespace) -> None:
    pid = property_id()
    prop = api_json("GET", f"{ADMIN}/properties/{pid}")
    print(f"display_name: {prop.get('displayName')}")
    print(f"time_zone: {prop.get('timeZone')}")
    print(f"currency: {prop.get('currencyCode')}")
    print(f"industry: {prop.get('industryCategory')}")
    streams = api_json("GET", f"{ADMIN}/properties/{pid}/dataStreams")
    print("\nData streams:")
    for stream in streams.get("dataStreams") or []:
        web = stream.get("webStreamData") or {}
        print(
            f"  - {stream.get('displayName')} | {stream.get('type')} | "
            f"{web.get('defaultUri')} | {web.get('measurementId')}"
        )


def cmd_list_conversion_events(_: argparse.Namespace) -> None:
    pid = property_id()
    data = api_json("GET", f"{ADMIN}/properties/{pid}/conversionEvents")
    print("Conversion events:")
    for ev in data.get("conversionEvents") or []:
        print(
            f"  - {ev.get('eventName')} | custom={ev.get('custom')} | "
            f"deletable={ev.get('deletable')}"
        )


def cmd_mark_conversion(args: argparse.Namespace) -> None:
    pid = property_id()
    created = api_json(
        "POST",
        f"{ADMIN}/properties/{pid}/conversionEvents",
        payload={"eventName": args.event},
    )
    print(f"OK marked conversion: {created.get('eventName')} ({created.get('name')})")


def main() -> None:
    parser = argparse.ArgumentParser(description="GA4 Admin API")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="Property + data streams")
    p_info.set_defaults(func=cmd_info)

    p_conv = sub.add_parser("conversions", help="List conversion events")
    p_conv.set_defaults(func=cmd_list_conversion_events)

    p_mark = sub.add_parser("mark-conversion", help="Create conversion event by name")
    p_mark.add_argument("event", help="e.g. purchase or view_item")
    p_mark.set_defaults(func=cmd_mark_conversion)

    args = parser.parse_args()
    ensure_credentials()
    args.func(args)


if __name__ == "__main__":
    main()
