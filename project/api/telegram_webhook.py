"""Telegram webhook ingress (prod)."""
import hmac
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from project.models import TelegramSettings
from project.telegram_bot import handle_update_async

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def telegram_webhook(request):
    settings = TelegramSettings.load()
    secret = (settings.webhook_secret or "").strip()
    # AI on + empty secret → refuse (open ingress). Telegram sends
    # X-Telegram-Bot-Api-Secret-Token when setWebhook(secret_token=…).
    if settings.ai_ready and not secret:
        logger.error("telegram webhook: ai_ready but webhook_secret empty")
        return HttpResponse(status=403)
    if secret:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(header, secret):
            return HttpResponse(status=403)

    try:
        update = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)

    # Products discussion FAQ — handle even when staff AI is off
    try:
        from social.services.telegram_products import handle_discussion_comment

        if handle_discussion_comment(update):
            return JsonResponse({"ok": True, "handled": "products_faq"})
    except Exception:
        logger.exception("products discussion handler failed")

    if not settings.ai_ready:
        return JsonResponse({"ok": True, "ignored": "ai_disabled"})

    handle_update_async(update)
    return JsonResponse({"ok": True})
