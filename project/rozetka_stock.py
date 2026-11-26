"""
Stock from our site -> Rozetka (PUT /items/mass-update), so a size sold on
the site (or edited in the admin) goes out of stock on Rozetka within one
poll instead of waiting for the hourly XML feed.

`sync_stock(client=None) -> {"updated": n, "errors": [...]}`. Never raises.

  * RozetkaItem maps Rozetka goods (rz_item_id) to our feed offer ids
    ("<product.pk>x<attr.pk>", see prom_feed.rozetka_offer_id). The map comes
    from GET /goods/all and is refreshed at most every REFRESH_HOURS.
  * The quantity sent is exactly the one the Rozetka feed publishes
    (`feed_stock_quantities` mirrors prom_feed.build_rozetka_offers); an offer
    the feed no longer has is sent as 0. Otherwise the API and the feed would
    keep overwriting each other.
  * Only offers whose quantity differs from RozetkaItem.last_quantity are
    sent, in batches of BATCH_SIZE. Price is never sent: it comes from the
    feed (site price * markup).
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

REFRESH_HOURS = 6
BATCH_SIZE = 50
GOODS_PAGE_SIZE = 100

# Our feed offer ids only; goods created on Rozetka by hand are left alone.
OFFER_ID_RE = re.compile(r"^(\d+)x(\d+)$")


# --- our side: what the feed publishes -------------------------------------

def feed_stock_quantities(product_ids=None) -> dict[str, int]:
    """{offer_id: stock_quantity} exactly as build_rozetka_offers would publish.

    Same products (merchant_feed.feed_products), same skips (no usable
    pictures, custom-length sizes, sizes without a price), same quantity
    (`max(int(attr.quantity or 0), 0)`), without building names and
    descriptions. `product_ids` narrows the query to the mapped products.
    """
    from project.merchant_feed import feed_products
    from project.prom_feed import rozetka_offer_id, rozetka_pictures

    products = feed_products()
    if product_ids is not None:
        products = products.filter(pk__in=list(product_ids))
    quantities: dict[str, int] = {}
    for product in products:
        if not rozetka_pictures(product):
            continue
        for attr in product.product_attr.all():
            if attr.custom_attribute or not attr.price:
                continue
            quantities[rozetka_offer_id(product, attr)] = max(int(attr.quantity or 0), 0)
    return quantities


def _product_id(offer_id: str) -> int | None:
    match = OFFER_ID_RE.match(offer_id or "")
    return int(match.group(1)) if match else None


# --- Rozetka side: goods map ----------------------------------------------

def _map_is_fresh(settings, now) -> bool:
    refreshed = settings.items_refreshed_at
    return bool(refreshed and now - refreshed < timedelta(hours=REFRESH_HOURS))


def refresh_items(client, settings, now=None) -> int:
    """GET /goods/all -> upsert RozetkaItem by rz_item_id. Returns rows seen.

    Raises RozetkaError (the caller records it). Rows without rz_item_id or
    with an offer id that is not ours are ignored. Mapping rows Rozetka no
    longer lists are removed (only after a full, non-empty scan), so a
    deleted Rozetka item is not retried forever.
    """
    from project.models import RozetkaItem, RozetkaSettings

    now = now or timezone.now()
    seen: dict[int, str] = {}
    for row in client.iter_goods(page_size=GOODS_PAGE_SIZE):
        if not isinstance(row, dict):
            continue
        try:
            rz_id = int(row.get("rz_item_id") or 0)
        except (TypeError, ValueError):
            continue
        offer_id = str(row.get("price_offer_id") or "").strip()
        if rz_id <= 0 or not OFFER_ID_RE.match(offer_id):
            continue
        seen[rz_id] = offer_id

    existing = {item.rz_item_id: item for item in RozetkaItem.objects.all()}
    to_create, to_update = [], []
    for rz_id, offer_id in seen.items():
        item = existing.get(rz_id)
        if item is None:
            to_create.append(RozetkaItem(rz_item_id=rz_id, offer_id=offer_id))
        elif item.offer_id != offer_id:
            item.offer_id = offer_id
            item.last_quantity = None  # other offer now: send it again
            to_update.append(item)
    if to_create:
        RozetkaItem.objects.bulk_create(to_create, ignore_conflicts=True)
    if to_update:
        RozetkaItem.objects.bulk_update(to_update, ["offer_id", "last_quantity"])
    if seen:
        RozetkaItem.objects.exclude(rz_item_id__in=list(seen)).delete()

    RozetkaSettings.objects.filter(pk=settings.pk).update(items_refreshed_at=now)
    settings.items_refreshed_at = now
    return len(seen)


# --- PUT /items/mass-update --------------------------------------------------

def _reason_text(value) -> str:
    """{"reason": [{"id": 1, "value": ["text"]}, ...]} -> "text; ..."."""
    reasons = value.get("reason") if isinstance(value, dict) else value
    parts: list[str] = []
    if isinstance(reasons, list):
        for reason in reasons:
            if isinstance(reason, dict):
                val = reason.get("value")
                if isinstance(val, list):
                    parts.extend(str(v) for v in val)
                elif val not in (None, ""):
                    parts.append(str(val))
                elif reason.get("id") is not None:
                    parts.append(f"reason {reason['id']}")
            else:
                parts.append(str(reason))
    elif reasons not in (None, ""):
        parts.append(str(reasons))
    return "; ".join(parts)[:200] or "rejected"


def _item_errors(errors) -> dict[int, str]:
    """Per-item validation errors are keyed by rz item id: {"102069758": {...}}."""
    if not isinstance(errors, dict) or not errors:
        return {}
    if not all(str(key).isdigit() for key in errors):
        return {}
    return {int(key): _reason_text(value) for key, value in errors.items()}


def _raw_put(client, body):
    from project.rozetka_api import BASE_URL, TIMEOUT_SECONDS, RozetkaError

    headers = {
        "Accept": "application/json",
        "Content-Language": "uk",
        "Authorization": f"Bearer {client.token}",
    }
    try:
        response = requests.request(
            "PUT",
            f"{BASE_URL}/items/mass-update",
            json=body,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RozetkaError(f"PUT /items/mass-update: {exc}") from exc
    try:
        data = response.json()
    except ValueError:
        data = None
    return response.status_code, data


def mass_update(client, items: list[dict]) -> dict[int, str]:
    """PUT /items/mass-update. Returns {rz_item_id: reason} for the items
    Rozetka rejected (the rest are applied); raises RozetkaError when the
    whole call failed.

    RozetkaClient.request() turns any `success: false` into a bare
    RozetkaError and drops the per-item errors, so a real client is called
    here directly (same headers, one re-login on a rejected token). Any other
    client object (tests, a wrapper) goes through its own mass_update().
    """
    from project.rozetka_api import RozetkaClient, RozetkaError, _error_text, _is_auth_failure

    if not isinstance(client, RozetkaClient):
        result = client.mass_update(items)
        return _item_errors(result.get("errors")) if isinstance(result, dict) else {}

    body = {"items": items}
    if not client.token:
        client.login()
    status, data = _raw_put(client, body)
    if _is_auth_failure(status, data):
        client.login()
        status, data = _raw_put(client, body)
        if _is_auth_failure(status, data):
            raise RozetkaError("PUT /items/mass-update: токен відхилено", auth=True)
    if not isinstance(data, dict):
        raise RozetkaError(f"PUT /items/mass-update: HTTP {status}, відповідь не JSON")
    if data.get("success"):
        return {}
    per_item = _item_errors(data.get("errors"))
    if per_item:
        return per_item
    raise RozetkaError(f"PUT /items/mass-update: {_error_text(data)}")


# --- the pass ---------------------------------------------------------------

def pending_changes(items) -> list[tuple]:
    """[(RozetkaItem, quantity)] whose feed quantity differs from last_quantity."""
    product_ids = {pid for pid in (_product_id(i.offer_id) for i in items) if pid}
    quantities = feed_stock_quantities(product_ids) if product_ids else {}
    changes = []
    for item in items:
        quantity = quantities.get(item.offer_id, 0)
        if item.last_quantity is None or item.last_quantity != quantity:
            changes.append((item, quantity))
    return changes


def push_changes(client, changes, now=None) -> tuple[int, list[str]]:
    from project.models import RozetkaItem

    now = now or timezone.now()
    updated = 0
    errors: list[str] = []
    for start in range(0, len(changes), BATCH_SIZE):
        batch = changes[start:start + BATCH_SIZE]
        payload = [
            {"item_rz_id": int(item.rz_item_id), "stock_quantity": int(quantity)}
            for item, quantity in batch
        ]
        try:
            rejected = mass_update(client, payload)
        except Exception as exc:
            logger.warning("rozetka stock: batch of %s failed: %s", len(batch), exc)
            errors.append(f"залишки ({len(batch)} шт.): {exc}"[:500])
            continue
        done = []
        for item, quantity in batch:
            if int(item.rz_item_id) in rejected:
                continue
            item.last_quantity = quantity
            item.synced_at = now
            done.append(item)
        if done:
            RozetkaItem.objects.bulk_update(done, ["last_quantity", "synced_at"])
        updated += len(done)
        if rejected:
            sample = "; ".join(f"{rz} ({reason})" for rz, reason in list(rejected.items())[:3])
            errors.append(f"залишки: Rozetka не прийняла {len(rejected)} шт.: {sample}"[:500])
    return updated, errors


def sync_stock(client=None) -> dict:
    """One stock pass for the poller. Never raises."""
    result = {"updated": 0, "errors": []}
    try:
        from project.models import RozetkaItem, RozetkaSettings
        from project.rozetka_api import RozetkaClient

        settings = RozetkaSettings.load()
        client = client or RozetkaClient(settings)
        now = timezone.now()

        if not _map_is_fresh(settings, now):
            try:
                refresh_items(client, settings, now)
            except Exception as exc:
                logger.warning("rozetka stock: goods list refresh failed: %s", exc)
                result["errors"].append(f"список товарів: {exc}"[:500])

        items = list(RozetkaItem.objects.all())
        if not items:
            return result
        changes = pending_changes(items)
        if not changes:
            return result
        updated, errors = push_changes(client, changes, now)
        result["updated"] = updated
        result["errors"].extend(errors)
    except Exception as exc:
        logger.exception("rozetka stock sync failed")
        result["errors"].append(str(exc)[:500])
    return result
