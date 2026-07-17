import datetime
import time
import os

import requests

from decouple import config

from .models import NovaPoshtaSettings

url = "https://api.novaposhta.ua/v2.0/json/"
# api_key = os.getenv("NOVA_POSHTA_API_KEY")


def get_api_key():
    settings_obj = NovaPoshtaSettings.objects.first()
    key = settings_obj.api_key if settings_obj and settings_obj.api_key else os.getenv("NOVA_POSHTA_API_KEY")
    if not key:
        raise RuntimeError("Nova Poshta API key is not configured (DB or NOVA_POSHTA_API_KEY).")
    return key


def get_full_response(model: str, method: str, properties: dict = None):
    """Paginate NP API until an empty page (Limit=150 per page)."""
    result = {"data": []}
    if not properties:
        properties = {}
    props = dict(properties)
    props.setdefault("Limit", "150")
    props["Page"] = "1"
    data = {
        "apiKey": get_api_key(),
        "modelName": model,
        "calledMethod": method,
        "methodProperties": props,
    }
    page = 1
    while True:
        data["methodProperties"]["Page"] = str(page)
        try:
            response = requests.post(url, json=data, timeout=120).json()
        except requests.exceptions.Timeout:
            continue
        errors = response.get("errors") or []
        if errors:
            raise RuntimeError(f"NP {method} page={page} errors: {errors}")
        chunk = response.get("data") or []
        if not chunk:
            break
        result["data"].extend(chunk)
        if page == 1 or page % 10 == 0:
            print(f"NP {method}: page={page} total={len(result['data'])}")
        page += 1
        # safety: NP cities/warehouses are large but finite
        if page > 5000:
            raise RuntimeError(f"NP {method}: pagination exceeded 5000 pages")
    return result


def get_response(model: str, method: str, properties: dict = {}, url: str = url):
    data = {
        "apiKey": get_api_key(),
        "modelName": model,
        "calledMethod": method,
        "methodProperties": properties,
    }
    response = requests.post(url, json=data).json()
    return response


def test_api():
    response = get_response("Address", "getSettlementTypes")
    if response["errors"]:
        raise Exception(response["errors"])
