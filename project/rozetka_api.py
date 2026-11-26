"""
Thin client for the Rozetka Marketplace Seller API.

Docs: https://api-seller.rozetka.com.ua/apidoc/ (data: /apidoc/api_data.js).
Base URL has a hyphen: api-seller.rozetka.com.ua.

  * POST /sites {username, password=base64(password)} -> content.access_token
  * every other call sends `Authorization: Bearer <token>`
  * answers are `{"success": bool, "content": ...}` or `{"success": false,
    "errors": {"message", "code", "description"}}`, usually with HTTP 200,
    so the body is checked, not only the status code
  * an expired token comes back as HTTP 401 (or errors.code 401): log in
    again once and repeat the call

The token is cached in RozetkaSettings.access_token (DB), so the web process
and the rozetka-poller share it. The client raises RozetkaError; the poller
(project/rozetka_orders.py) catches it and records last_error.
"""

from __future__ import annotations

import base64
import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api-seller.rozetka.com.ua"
TIMEOUT_SECONDS = 20

# GET /orders/search ?expand=... : everything the importer needs in one call.
ORDER_EXPAND = "user,delivery,purchases,payment_type_name,delivery_service"

# OrderStatus.status_group: 1 in progress, 2 successful, 3 failed (cancelled).
STATUS_GROUP_IN_PROGRESS = 1
STATUS_GROUP_SUCCESS = 2
STATUS_GROUP_FAILED = 3

# order-statuses: "1 / Нове замовлення" (see /order-statuses/search).
STATUS_NEW = 1


class RozetkaError(Exception):
    """API or transport failure. `auth` marks a rejected/expired token."""

    def __init__(self, message: str, *, auth: bool = False):
        super().__init__(message)
        self.auth = auth


def encode_password(password: str) -> str:
    return base64.b64encode((password or "").encode("utf-8")).decode("ascii")


def _error_text(data) -> str:
    errors = (data or {}).get("errors") if isinstance(data, dict) else None
    if isinstance(errors, dict):
        message = errors.get("message") or ""
        description = errors.get("description") or ""
        code = errors.get("code")
        details = errors.get("details")
        parts = [str(p) for p in (message, description) if p]
        text = " - ".join(parts) or "unknown error"
        if code not in (None, ""):
            text = f"[{code}] {text}"
        if details:
            text = f"{text} {str(details)[:300]}"
        return text
    if errors:
        return str(errors)[:500]
    return "unknown error"


def _is_auth_failure(status_code: int, data) -> bool:
    if status_code == 401:
        return True
    errors = data.get("errors") if isinstance(data, dict) else None
    if isinstance(errors, dict):
        if str(errors.get("code")) == "401":
            return True
        if str(errors.get("message") or "").lower() in ("unauthorized", "unauthorised"):
            return True
    return False


class RozetkaClient:
    def __init__(self, settings=None):
        from .models import RozetkaSettings

        self.settings = settings or RozetkaSettings.load()
        self.token = (self.settings.access_token or "").strip()

    # --- auth -------------------------------------------------------------

    def login(self) -> str:
        username = (self.settings.username or "").strip()
        password = self.settings.password or ""
        if not username or not password:
            raise RozetkaError("Не задано логін або пароль Rozetka")
        data = self._send(
            "POST",
            "/sites",
            json={"username": username, "password": encode_password(password)},
            auth=False,
        )
        content = data.get("content") or {}
        token = (content.get("access_token") or "").strip() if isinstance(content, dict) else ""
        if not token:
            raise RozetkaError("Rozetka не повернула access_token")
        self.token = token
        self._store_token(token)
        return token

    def _store_token(self, token: str) -> None:
        from .models import RozetkaSettings

        try:
            RozetkaSettings.objects.filter(pk=self.settings.pk).update(access_token=token)
        except Exception:
            logger.exception("rozetka: could not cache access token")
        self.settings.access_token = token

    # --- transport --------------------------------------------------------

    def _send(self, method, path, *, params=None, json=None, auth=True) -> dict:
        headers = {"Accept": "application/json", "Content-Language": "uk"}
        if auth:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = requests.request(
                method,
                f"{BASE_URL}{path}",
                params=params,
                json=json,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise RozetkaError(f"{method} {path}: {exc}") from exc
        try:
            data = response.json()
        except ValueError:
            data = None
        if auth and _is_auth_failure(response.status_code, data):
            raise RozetkaError(f"{method} {path}: токен відхилено", auth=True)
        if not isinstance(data, dict):
            raise RozetkaError(f"{method} {path}: HTTP {response.status_code}, відповідь не JSON")
        if not data.get("success"):
            raise RozetkaError(f"{method} {path}: {_error_text(data)}")
        return data

    def request(self, method, path, *, params=None, json=None):
        """Authorized call; one re-login and retry when the token is rejected."""
        if not self.token:
            self.login()
        try:
            data = self._send(method, path, params=params, json=json)
        except RozetkaError as exc:
            if not exc.auth:
                raise
            self.login()
            data = self._send(method, path, params=params, json=json)
        return data.get("content")

    # --- orders -----------------------------------------------------------

    def search_orders(self, *, created_from: date | str | None = None, page: int = 1,
                      expand: str = ORDER_EXPAND, **filters) -> tuple[list[dict], dict]:
        """GET /orders/search -> (orders, _meta). Newest first."""
        params = {"expand": expand, "sort": "-id", "page": page}
        if created_from:
            params["created_from"] = (
                created_from.isoformat() if isinstance(created_from, date) else created_from
            )
        params.update(filters)
        content = self.request("GET", "/orders/search", params=params) or {}
        return list(content.get("orders") or []), dict(content.get("_meta") or {})

    def iter_orders(self, *, max_pages: int = 20, **kwargs):
        """All pages of search_orders (bounded, so a bad _meta cannot loop forever)."""
        page = 1
        while page <= max_pages:
            orders, meta = self.search_orders(page=page, **kwargs)
            yield from orders
            page_count = int(meta.get("pageCount") or 1)
            if not orders or page >= page_count:
                return
            page += 1

    def get_order(self, order_id: int, expand: str = ORDER_EXPAND) -> dict:
        """GET /orders/{id}."""
        content = self.request("GET", f"/orders/{int(order_id)}", params={"expand": expand})
        return content or {}

    def change_status(self, order_id: int, status: int, *, ttn: str | None = None,
                      seller_comment: str | None = None) -> dict:
        """PUT /orders/{id}: new status (ttn is required by Rozetka for 3 and 61)."""
        body = {"status": int(status)}
        if ttn:
            body["ttn"] = ttn
        if seller_comment:
            body["seller_comment"] = seller_comment
        content = self.request("PUT", f"/orders/{int(order_id)}", json=body)
        return content or {}

    def order_statuses(self) -> list[dict]:
        """GET /order-statuses/search (content.orderStatus)."""
        content = self.request(
            "GET", "/order-statuses/search", params={"expand": "status_available"}
        ) or {}
        return list(content.get("orderStatus") or [])

    # --- generic pagination ------------------------------------------------

    def iter_pages(self, path: str, key: str, params: dict | None = None, *, max_pages: int = 50):
        """Yield rows of content[key] over all pages of a GET search endpoint."""
        page = 1
        while page <= max_pages:
            query = dict(params or {})
            query["page"] = page
            content = self.request("GET", path, params=query) or {}
            rows = list(content.get(key) or [])
            yield from rows
            meta = content.get("_meta") or {}
            page_count = int(meta.get("pageCount") or 1)
            if not rows or page >= page_count:
                return
            page += 1

    # --- buyer messages (Messages, ItemComments, Calls) --------------------

    def iter_chats(self, *, msg_type: str = "items", updated_from: date | str | None = None,
                   expand: str = "messages,item,user_fio,order_data", max_pages: int = 5):
        """GET /messages/search: msgType "items" (questions about goods / to the
        seller) or "orders" (chats inside an order). content.chats[]."""
        params = {"msgType": msg_type, "expand": expand, "sort": "-updated"}
        if updated_from:
            params["updated_from"] = (
                updated_from.isoformat() if isinstance(updated_from, date) else updated_from
            )
        yield from self.iter_pages("/messages/search", "chats", params, max_pages=max_pages)

    def get_chat(self, chat_id: int, expand: str = "messages,item") -> dict:
        """GET /messages/{id}."""
        return self.request("GET", f"/messages/{int(chat_id)}", params={"expand": expand}) or {}

    def iter_item_comments(self, *, created_from: date | str | None = None,
                           expand: str = "children", max_pages: int = 5):
        """GET /item-comments/search (questions and reviews under goods).
        content.itemComments[]."""
        params = {"sort": "-created", "expand": expand}
        if created_from:
            params["createdFrom"] = (
                created_from.isoformat() if isinstance(created_from, date) else created_from
            )
        yield from self.iter_pages("/item-comments/search", "itemComments", params, max_pages=max_pages)

    def iter_calls(self, *, created_from: date | str | None = None, max_pages: int = 5):
        """GET /calls/search (customer requests passed on by Rozetka). content.calls[]."""
        params = {"sort": "-id"}
        if created_from:
            params["created_from"] = (
                created_from.isoformat() if isinstance(created_from, date) else created_from
            )
        yield from self.iter_pages("/calls/search", "calls", params, max_pages=max_pages)

    # --- goods and stock --------------------------------------------------

    def iter_goods(self, *, page_size: int = 100, max_pages: int = 100, **filters):
        """GET /goods/all: our goods on Rozetka (rz_item_id, price_offer_id, ...).
        content.items[]."""
        params = {"pageSize": page_size}
        params.update(filters)
        yield from self.iter_pages("/goods/all", "items", params, max_pages=max_pages)

    def mass_update(self, items: list[dict]):
        """PUT /items/mass-update: [{"item_rz_id": int, "stock_quantity": int, "price"?: int}]."""
        return self.request("PUT", "/items/mass-update", json={"items": items})
