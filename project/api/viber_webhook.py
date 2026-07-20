"""Viber webhook ingress.

Viber відхиляє Post API (`status: 10, webhookNotSet`), поки в акаунта
не зареєстрований webhook — навіть якщо вхідні події нам не потрібні.
Цей endpoint існує саме для цього: приймає callback-и, логує і завжди
відповідає 200 (інакше Viber вважає webhook неробочим і знімає його).
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


def _signature_ok(raw_body: bytes, signature: str) -> bool:
    """X-Viber-Content-Signature = HMAC-SHA256(auth_token, body)."""
    token = (getattr(settings, "VIBER_AUTH_TOKEN", "") or "").strip()
    if not token or not signature:
        return False
    expected = hmac.new(token.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


@csrf_exempt
def viber_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    signature = request.headers.get("X-Viber-Content-Signature", "")
    if not _signature_ok(request.body, signature):
        # Не блокуємо: endpoint не має side-effects, а 4xx у відповідь
        # змусить Viber зняти webhook і Post API знову впаде.
        logger.warning("viber webhook: signature mismatch")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse("ok")

    event = (payload.get("event") or "").strip()
    if event == "webhook":
        logger.info("viber webhook: validation callback ok")
    elif event in ("message", "subscribed", "unsubscribed", "conversation_started"):
        logger.info("viber webhook: event=%s", event)
    elif event == "failed":
        logger.error("viber webhook: delivery failed %s", str(payload)[:300])

    return HttpResponse("ok")
