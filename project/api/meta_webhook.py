"""Meta (IG/FB) webhook ingress — дзеркало коментів у staff topic.

GET  — верифікація підписки (hub.challenge, verify token з .env).
POST — події; підпис X-Hub-Signature-256 перевіряється, якщо є META_APP_SECRET.
Завжди відповідаємо швидко і 200 — інакше Meta ретраїть та відключає webhook.
"""

import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


@csrf_exempt
def meta_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode", "")
        token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        expected = (
            getattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "") or ""
        ).strip()
        if mode == "subscribe" and expected and token == expected:
            return HttpResponse(challenge, content_type="text/plain")
        logger.warning("meta webhook verify failed: mode=%s", mode)
        return HttpResponse(status=403)

    if request.method != "POST":
        return HttpResponse(status=405)

    from social.services.meta_comments import handle_meta_webhook, verify_signature

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(request.body, signature):
        logger.warning("meta webhook: bad signature")
        return HttpResponse(status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)

    try:
        sent = handle_meta_webhook(payload)
        if sent:
            logger.info("meta webhook: %d staff alert(s) sent", sent)
    except Exception:
        # 200 попри помилку — щоб Meta не вимкнула підписку через ретраї
        logger.exception("meta webhook handling failed")

    return HttpResponse("ok")
