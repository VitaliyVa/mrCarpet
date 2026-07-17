import os
import time

import requests

from .models import NovaPoshtaSettings

url = "https://api.novaposhta.ua/v2.0/json/"


def get_api_key():
    settings_obj = NovaPoshtaSettings.objects.first()
    key = (
        settings_obj.api_key
        if settings_obj and settings_obj.api_key
        else os.getenv("NOVA_POSHTA_API_KEY")
    )
    if not key:
        raise RuntimeError(
            "Nova Poshta API key is not configured (DB or NOVA_POSHTA_API_KEY)."
        )
    return key


def _is_rate_limit(errors) -> bool:
    text = " ".join(str(e) for e in (errors or [])).lower()
    return "many request" in text or "too many" in text or "rate" in text


def get_response(model: str, method: str, properties: dict = None, *, max_retries: int = 8):
    """Single NP call with rate-limit retries (original helper + resilience)."""
    if properties is None:
        properties = {}
    data = {
        "apiKey": get_api_key(),
        "modelName": model,
        "calledMethod": method,
        "methodProperties": properties,
    }
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, json=data, timeout=120).json()
        except requests.exceptions.Timeout:
            time.sleep(min(2**attempt, 30))
            continue
        errors = response.get("errors") or []
        if _is_rate_limit(errors):
            wait = min(2**attempt, 60)
            print(f"NP {method}: rate-limit attempt={attempt}/{max_retries}, sleep {wait}s")
            time.sleep(wait)
            continue
        return response
    raise RuntimeError(f"NP {method}: rate-limit retries exhausted")


def get_full_response(model: str, method: str, properties: dict = None):
    """
    Paginate NP API (original behaviour), plus delay + rate-limit retry.
    Page is int like the original implementation.
    """
    result = {"data": []}
    if not properties:
        properties = {}
    props = dict(properties)
    data = {
        "apiKey": get_api_key(),
        "modelName": model,
        "calledMethod": method,
        "methodProperties": props,
    }
    data["methodProperties"]["Page"] = 1
    while True:
        page = data["methodProperties"]["Page"]
        response = None
        for attempt in range(1, 9):
            try:
                response = requests.post(url, json=data, timeout=120).json()
            except requests.exceptions.Timeout:
                time.sleep(min(2**attempt, 30))
                continue
            errors = response.get("errors") or []
            if _is_rate_limit(errors):
                wait = min(2**attempt, 60)
                print(
                    f"NP {method}: rate-limit page={page} "
                    f"attempt={attempt}/8, sleep {wait}s"
                )
                time.sleep(wait)
                continue
            if errors:
                # Original swallowed odd pages; still surface hard errors
                raise RuntimeError(f"NP {method} page={page} errors: {errors}")
            break
        else:
            raise RuntimeError(f"NP {method} page={page}: rate-limit retries exhausted")

        chunk = (response or {}).get("data") or []
        if not chunk:
            break
        result["data"].extend(chunk)
        data["methodProperties"]["Page"] += 1
        print(data["methodProperties"]["Page"])
        time.sleep(0.4)
        if data["methodProperties"]["Page"] > 5000:
            raise RuntimeError(f"NP {method}: pagination exceeded 5000 pages")
    return result


def test_api():
    response = get_response("Address", "getSettlementTypes")
    if response.get("errors"):
        raise Exception(response["errors"])
