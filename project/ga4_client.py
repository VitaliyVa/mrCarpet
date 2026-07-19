"""GA4 Data API client for Django (service account JWT, no google-* SDKs)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

import jwt
from django.conf import settings

logger = logging.getLogger(__name__)

READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"

FUNNEL_EVENTS = (
    "view_item",
    "add_to_cart",
    "view_cart",
    "begin_checkout",
    "add_shipping_info",
    "add_payment_info",
    "purchase",
)

_token_cache: dict[str, Any] = {"token": "", "exp": 0}


class Ga4ClientError(Exception):
    """User-facing / tool-facing GA4 failure."""


def property_id() -> str:
    return (getattr(settings, "GA4_PROPERTY_ID", "") or "").strip()


def _sa_info() -> dict:
    raw_json = (getattr(settings, "GA4_SERVICE_ACCOUNT_JSON", "") or "").strip()
    if raw_json:
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise Ga4ClientError("GA4_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    path = (getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", "") or "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except OSError as exc:
            raise Ga4ClientError(f"Cannot read GA4 credentials file: {path}") from exc
        except json.JSONDecodeError as exc:
            raise Ga4ClientError("GA4 credentials file is not valid JSON") from exc

    raise Ga4ClientError(
        "GA4 не налаштовано: задайте GA4_SERVICE_ACCOUNT_JSON "
        "або GOOGLE_APPLICATION_CREDENTIALS + GA4_PROPERTY_ID"
    )


def ga4_configured() -> bool:
    if not property_id().isdigit():
        return False
    try:
        info = _sa_info()
    except Ga4ClientError:
        return False
    return bool(info.get("client_email") and info.get("private_key"))


def access_token() -> str:
    now = int(time.time())
    if _token_cache["token"] and _token_cache["exp"] > now + 60:
        return _token_cache["token"]

    info = _sa_info()
    assertion = jwt.encode(
        {
            "iss": info["client_email"],
            "scope": READONLY_SCOPE,
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        },
        info["private_key"],
        algorithm="RS256",
    )
    body = urlparse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }
    ).encode()
    req = urlrequest.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urlerror.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise Ga4ClientError(f"GA4 OAuth failed HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise Ga4ClientError(f"GA4 OAuth failed: {exc}") from exc

    token = data.get("access_token")
    if not token:
        raise Ga4ClientError("GA4 OAuth: no access_token")
    _token_cache["token"] = token
    _token_cache["exp"] = now + int(data.get("expires_in") or 3600)
    return token


def api_json(method: str, url: str, *, payload: dict | None = None) -> dict:
    token = access_token()
    data = None if payload is None else json.dumps(payload).encode()
    req = urlrequest.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:800]
        raise Ga4ClientError(f"GA4 API HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise Ga4ClientError(f"GA4 API failed: {exc}") from exc


def _metric_row(resp: dict, labels: list[str]) -> dict[str, str]:
    rows = resp.get("rows") or []
    if not rows:
        return {k: "0" for k in labels}
    cells = rows[0].get("metricValues") or []
    out: dict[str, str] = {}
    for label, cell in zip(labels, cells):
        out[label] = (cell or {}).get("value") or "0"
    for label in labels:
        out.setdefault(label, "0")
    return out


def fetch_overview(days: int) -> dict[str, Any]:
    pid = property_id()
    if not pid.isdigit():
        raise Ga4ClientError("GA4_PROPERTY_ID must be digits")
    start = f"{int(days)}daysAgo"
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
    kpis = _metric_row(
        overview, ["activeUsers", "sessions", "pageViews", "engagedSessions"]
    )

    pages_resp = api_json(
        "POST",
        base,
        payload={
            "dateRanges": [{"startDate": start, "endDate": "today"}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}],
            "limit": "10",
        },
    )
    pages = []
    for row in pages_resp.get("rows") or []:
        pages.append(
            {
                "path": row["dimensionValues"][0]["value"],
                "views": row["metricValues"][0]["value"],
                "users": row["metricValues"][1]["value"],
            }
        )
    return {"days": days, "kpis": kpis, "top_pages": pages}


def fetch_daily_trend(days: int) -> list[dict[str, Any]]:
    """Per-day users / sessions / pageViews."""
    pid = property_id()
    start = f"{int(days)}daysAgo"
    base = f"https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"
    resp = api_json(
        "POST",
        base,
        payload={
            "dateRanges": [{"startDate": start, "endDate": "today"}],
            "dimensions": [{"name": "date"}],
            "metrics": [
                {"name": "activeUsers"},
                {"name": "sessions"},
                {"name": "screenPageViews"},
            ],
            "orderBys": [{"dimension": {"dimensionName": "date"}, "desc": False}],
            "limit": "31",
        },
    )
    out: list[dict[str, Any]] = []
    for row in resp.get("rows") or []:
        raw = row["dimensionValues"][0]["value"]  # YYYYMMDD
        label = f"{raw[6:8]}.{raw[4:6]}" if len(raw) == 8 else raw
        out.append(
            {
                "date": raw,
                "label": label,
                "users": int(float(row["metricValues"][0]["value"] or 0)),
                "sessions": int(float(row["metricValues"][1]["value"] or 0)),
                "views": int(float(row["metricValues"][2]["value"] or 0)),
            }
        )
    return out


def fetch_ecommerce(days: int) -> dict[str, Any]:
    pid = property_id()
    start = f"{int(days)}daysAgo"
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
    by_name: dict[str, dict[str, str]] = {}
    for row in events.get("rows") or []:
        name = row["dimensionValues"][0]["value"]
        by_name[name] = {
            "events": row["metricValues"][0]["value"],
            "users": row["metricValues"][1]["value"],
        }
    funnel = []
    for name in FUNNEL_EVENTS:
        cell = by_name.get(name) or {"events": "0", "users": "0"}
        funnel.append(
            {
                "event": name,
                "events": int(float(cell["events"] or 0)),
                "users": int(float(cell["users"] or 0)),
            }
        )

    revenue = {
        "purchaseRevenue": "0",
        "ecommercePurchases": "0",
        "averagePurchaseRevenue": "0",
    }
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
        revenue = _metric_row(
            rev,
            ["purchaseRevenue", "ecommercePurchases", "averagePurchaseRevenue"],
        )
    except Ga4ClientError as exc:
        logger.info("GA4 revenue metrics unavailable: %s", exc)

    sources: list[dict[str, Any]] = []
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
                "limit": "10",
                "orderBys": [
                    {"metric": {"metricName": "sessions"}, "desc": True}
                ],
            },
        )
        for row in src.get("rows") or []:
            sources.append(
                {
                    "source": row["dimensionValues"][0]["value"],
                    "medium": row["dimensionValues"][1]["value"],
                    "sessions": int(float(row["metricValues"][0]["value"] or 0)),
                    "purchases": int(float(row["metricValues"][1]["value"] or 0)),
                }
            )
    except Ga4ClientError as exc:
        logger.info("GA4 sources unavailable: %s", exc)

    return {
        "days": days,
        "funnel": funnel,
        "revenue": revenue,
        "sources": sources,
    }


def fetch_realtime() -> dict[str, Any]:
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
    screens = []
    total = 0
    for row in resp.get("rows") or []:
        users = int(float(row["metricValues"][0]["value"] or 0))
        total += users
        screens.append(
            {
                "screen": row["dimensionValues"][0]["value"],
                "users": users,
            }
        )
    return {"active_users": total, "screens": screens}


def fetch_dashboard(days: int) -> dict[str, Any]:
    """Combined payload for Telegram charts."""
    overview = fetch_overview(days)
    ecom = fetch_ecommerce(days)
    daily: list[dict[str, Any]] = []
    try:
        daily = fetch_daily_trend(days)
    except Ga4ClientError as exc:
        logger.info("GA4 daily trend unavailable: %s", exc)
    return {
        "days": days,
        "kpis": overview["kpis"],
        "top_pages": overview["top_pages"],
        "funnel": ecom["funnel"],
        "revenue": ecom["revenue"],
        "sources": ecom["sources"],
        "daily": daily,
    }
