"""Remember which ad click brought the buyer, so a real sale can be reported back.

Google Ads can only learn from a sale it can tie to a click. GA4 imports do
that for us only while the sale is reported at once, and cash on delivery is
not a sale until the parcel is picked up. Keeping the click id on the order
lets the shop upload paid orders to Ads later (offline conversions, see
order/ads_conversions.py) and lets the main session correct refused parcels.

Capture happens server-side on the landing request:

* gclid (web), gbraid (iOS app to web), wbraid (iOS web to web) are kept
  together, newest click wins, the time of that click is kept with them;
* utm_source / utm_medium / utm_campaign are kept as a separate group, so a
  later newsletter visit does not wipe a still valid Ads click.

The cookie is signed (no DB row per visitor, bots stay cheap) and lives 90
days, the longest Ads click-through window. At checkout the gtag conversion
linker cookies (_gcl_aw, _gcl_gb) serve as a fallback for visitors whose
landing was before this code shipped.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.core import signing

COOKIE_NAME = "mrc_ads"
COOKIE_SALT = "project.ad_attribution"
COOKIE_MAX_AGE = 90 * 24 * 60 * 60

CLICK_KEYS = ("gclid", "gbraid", "wbraid")
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign")

# Click ids are url-safe tokens. Anything else is junk or an injection try,
# and a broken id only makes the Ads upload reject the row.
_CLICK_ID_RE = re.compile(r"^[A-Za-z0-9_\-.~]{8,255}$")
_UTM_MAX = 150

_SKIP_PREFIXES = ("/admin/", "/api/", "/static/", "/media/", "/feeds/")


def _clean_click_id(value) -> str:
    value = (value or "").strip()
    return value if _CLICK_ID_RE.match(value) else ""


def _clean_utm(value) -> str:
    value = (value or "").strip()
    # Control characters would break the CSV export and the admin view.
    value = "".join(ch for ch in value if ch.isprintable())
    return value[:_UTM_MAX]


def params_from_query(query) -> dict:
    """Pull the attribution groups out of a QueryDict / dict of GET params."""
    out: dict = {}
    clicks = {k: _clean_click_id(query.get(k)) for k in CLICK_KEYS}
    if any(clicks.values()):
        out.update(clicks)
        out["click_ts"] = int(time.time())
    utms = {k: _clean_utm(query.get(k)) for k in UTM_KEYS}
    if any(utms.values()):
        out.update(utms)
    return out


def read_cookie(request) -> dict:
    raw = getattr(request, "COOKIES", {}).get(COOKIE_NAME)
    if not raw:
        return {}
    try:
        data = signing.loads(raw, salt=COOKIE_SALT, max_age=COOKIE_MAX_AGE)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def merge(current: dict, fresh: dict) -> dict:
    """Replace a whole group when the landing carries it, keep the other one."""
    merged = dict(current or {})
    if any(fresh.get(k) for k in CLICK_KEYS):
        for k in (*CLICK_KEYS, "click_ts"):
            merged.pop(k, None)
        merged.update({k: fresh[k] for k in (*CLICK_KEYS, "click_ts") if fresh.get(k)})
    if any(fresh.get(k) for k in UTM_KEYS):
        for k in UTM_KEYS:
            merged.pop(k, None)
        merged.update({k: fresh[k] for k in UTM_KEYS if fresh.get(k)})
    return merged


def _gcl_cookie_value(raw) -> tuple[str, int | None]:
    """_gcl_aw / _gcl_gb look like GCL.<unix ts>.<click id>."""
    parts = str(raw or "").strip().split(".", 2)
    if len(parts) != 3 or parts[0] != "GCL":
        return "", None
    ts = int(parts[1]) if parts[1].isdigit() else None
    return _clean_click_id(parts[2]), ts


def order_fields_from_request(request) -> dict:
    """Order field values for the attribution this visitor carries.

    Returns only non-empty values, so the caller can pass the dict straight to
    an update() without blanking anything.
    """
    if request is None:
        return {}
    data = read_cookie(request)
    if not any(data.get(k) for k in CLICK_KEYS):
        cookies = getattr(request, "COOKIES", {}) or {}
        gclid, ts_aw = _gcl_cookie_value(cookies.get("_gcl_aw"))
        gbraid, ts_gb = _gcl_cookie_value(cookies.get("_gcl_gb"))
        if gclid:
            data["gclid"] = gclid
        if gbraid:
            data["gbraid"] = gbraid
        ts = ts_aw if gclid else ts_gb
        if (gclid or gbraid) and ts:
            data["click_ts"] = ts

    fields = {k: data[k] for k in (*CLICK_KEYS, *UTM_KEYS) if data.get(k)}
    ts = data.get("click_ts")
    if fields.keys() & set(CLICK_KEYS) and isinstance(ts, int) and ts > 0:
        try:
            fields["ad_click_at"] = datetime.fromtimestamp(ts, tz=dt_timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    return fields


class AdAttributionMiddleware:
    """Store click ids / utm from the landing URL in a signed cookie."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._remember(request, response)
        except Exception:
            # Attribution must never break a page.
            pass
        return response

    @staticmethod
    def _remember(request, response):
        if request.method != "GET" or not request.GET:
            return
        if request.path.startswith(_SKIP_PREFIXES):
            return
        if response.status_code >= 500:
            return
        fresh = params_from_query(request.GET)
        if not fresh:
            return
        merged = merge(read_cookie(request), fresh)
        if merged == read_cookie(request):
            return
        response.set_cookie(
            COOKIE_NAME,
            signing.dumps(merged, salt=COOKIE_SALT, compress=True),
            max_age=COOKIE_MAX_AGE,
            secure=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
            httponly=True,
            samesite="Lax",
        )
