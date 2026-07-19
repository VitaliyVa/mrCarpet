#!/usr/bin/env python3
"""Verify GA4 Data + Admin REST access with the service account."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _auth import api_json  # noqa: E402
from _env import credentials_path, ensure_credentials, property_id  # noqa: E402


def main() -> None:
    creds = ensure_credentials()
    pid = property_id()
    print(f"credentials: {creds}")
    print(f"property_id: {pid}")

    prop = api_json("GET", f"https://analyticsadmin.googleapis.com/v1beta/properties/{pid}")
    print(
        f"Admin OK — display_name={prop.get('displayName')!r} "
        f"timeZone={prop.get('timeZone')}"
    )

    report = api_json(
        "POST",
        f"https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport",
        payload={
            "dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
            "dimensions": [{"name": "date"}],
            "metrics": [{"name": "activeUsers"}, {"name": "sessions"}],
            "limit": "3",
        },
    )
    rows = report.get("rows") or []
    print(f"Data OK — rows={len(rows)}")
    for row in rows:
        dims = [d.get("value") for d in row.get("dimensionValues", [])]
        mets = [m.get("value") for m in row.get("metricValues", [])]
        print(" ", dims, mets)
    print("service_account_email hint:", end=" ")
    import json

    print(json.loads(credentials_path().read_text(encoding="utf-8")).get("client_email"))
    print("SMOKE_PASS")


if __name__ == "__main__":
    main()
