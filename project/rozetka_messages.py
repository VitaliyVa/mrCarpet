"""
Buyer messages from Rozetka -> Telegram. Implemented by the messages agent.

`notify_new_messages(client=None) -> {"sent": n, "errors": [...]}`. Never raises.
"""

from __future__ import annotations


def notify_new_messages(client=None) -> dict:
    return {"sent": 0, "errors": []}
