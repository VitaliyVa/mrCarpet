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
    if secret:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(header, secret):
            return HttpResponse(status=403)

    if not settings.ai_ready:
        return JsonResponse({"ok": True, "ignored": "ai_disabled"})

    try:
        update = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)

    handle_update_async(update)
    return JsonResponse({"ok": True})
