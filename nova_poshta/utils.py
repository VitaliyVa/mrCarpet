import datetime
import time

import requests

from decouple import config


url = "https://api.novaposhta.ua/v2.0/json/"
api_key = "75e54d771582e1d7d1a29aeddabcea02"


def get_full_response(model: str, method: str, properties: dict = None):
    result = {"data": []}
    if not properties:
        properties = {}
    data = {
        "apiKey": api_key,
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
        "apiKey": api_key,
        "modelName": model,
        "calledMethod": method,
        "methodProperties": properties,
    }
    response = None
    while not response:
        try:
            response = requests.post(url, json=data).json()
        except requests.exceptions.Timeout:
            continue
    return response


def test_api():
    response = get_response("Address", "getSettlementTypes")
    if response["errors"]:
        raise Exception(response["errors"])
