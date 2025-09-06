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
    result = {"data": []}
    if not properties:
        properties = {}
    data = {
        "apiKey": get_api_key(),
        "modelName": model,
        "calledMethod": method,
        "methodProperties": properties,
    }
    data["methodProperties"]["Page"] = 1
    while True:
        try:
            response = requests.post(url, json=data).json()
            for obj in response["data"]:
                result["data"].append(obj)
            if not response["data"]:
                break
            data["methodProperties"]["Page"] += 1
            print(data["methodProperties"]["Page"])
        except requests.exceptions.Timeout:
            continue
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
