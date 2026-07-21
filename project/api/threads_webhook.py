"""
Threads webhook ingress — replies mirrored into the video staff topic.

GET  — subscription handshake (hub.challenge against THREADS_WEBHOOK_VERIFY_TOKEN).
POST — events; X-Hub-Signature-256 checked against the *Threads* app secret.

Always answers 200 on a handled POST, even when processing failed: Meta
retries non-200 responses and eventually disables the subscription, which
would cost us every future reply to save one error code.
"""

import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


@csrf_exempt
def threads_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode", "")
        token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        expected = (
            getattr(settings, "THREADS_WEBHOOK_VERIFY_TOKEN", "") or ""
        ).strip()
        if mode == "subscribe" and expected and token == expected:
            return HttpResponse(challenge, content_type="text/plain")
        logger.warning("threads webhook verify failed: mode=%s", mode)
        return HttpResponse(status=403)

    if request.method != "POST":
        return HttpResponse(status=405)

    from social.services.threads_comments import (
        handle_threads_webhook,
        verify_signature,
    )

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(request.body, signature):
        logger.warning("threads webhook: bad signature")
        return HttpResponse(status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)

    try:
        sent = handle_threads_webhook(payload)
        if sent:
            logger.info("threads webhook: %d staff alert(s) sent", sent)
    except Exception:
        logger.exception("threads webhook handling failed")

    return HttpResponse("ok")
