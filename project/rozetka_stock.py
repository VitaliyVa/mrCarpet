"""
Stock from our site -> Rozetka (PUT /items/mass-update). Implemented by the stock agent.

`sync_stock(client=None) -> {"updated": n, "errors": [...]}`. Never raises.
"""

from __future__ import annotations


def sync_stock(client=None) -> dict:
    return {"updated": 0, "errors": []}
