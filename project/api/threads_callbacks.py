"""
Threads deauthorize and data-deletion callbacks.

Meta requires both URLs before a Threads app can be configured, and they are
not a formality: when the account owner revokes our access from inside
Threads, this is the only signal we get. Without it the stored token quietly
stops working and the daily run reports a confusing API error instead of
"nobody authorized us any more".

Both endpoints receive a `signed_request` — `base64url(signature).base64url(payload)`
signed with the *Threads* app secret. The signature is verified before
anything is acted on; an unsigned POST to a public URL must never be able to
delete our credentials.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from typing import Any

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from social.services.threads_auth import app_secret

logger = logging.getLogger(__name__)


class SignedRequestError(ValueError):
    pass


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def parse_signed_request(signed_request: str, secret: str) -> dict[str, Any]:
    """
    Verify and decode Meta's signed_request.

    Raises SignedRequestError on anything suspicious — a bad signature is not
    a reason to guess at the payload.
    """
    if not secret:
        raise SignedRequestError("THREADS_APP_SECRET is empty")
    if not signed_request or "." not in signed_request:
        raise SignedRequestError("malformed signed_request")

    encoded_sig, _, encoded_payload = signed_request.partition(".")
    try:
        signature = _b64url_decode(encoded_sig)
        payload = json.loads(_b64url_decode(encoded_payload))
    except Exception as exc:
        raise SignedRequestError(f"undecodable signed_request: {exc}") from exc

    algorithm = str(payload.get("algorithm") or "").upper()
    if algorithm != "HMAC-SHA256":
        raise SignedRequestError(f"unexpected algorithm: {algorithm}")

    expected = hmac.new(
        secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256
    ).digest()
    # Constant-time: a timing oracle here would leak the signature byte by byte.
    if not hmac.compare_digest(expected, signature):
        raise SignedRequestError("signature mismatch")

    return payload


def _forget_token(reason: str, user_id: str = "") -> None:
    """
    Drop the stored credentials so the admin tells the truth.

    Deliberately clears rather than deletes the row: the singleton carries the
    last_error that explains why posting stopped.
    """
    from social.models import ThreadsToken

    token = ThreadsToken.load()
    if user_id and token.user_id and token.user_id != user_id:
        logger.warning(
            "Threads callback for a different user_id (%s vs %s) — ignoring",
            user_id,
            token.user_id,
        )
        return

    token.access_token = ""
    token.expires_at = None
    token.last_error = reason[:2000]
    token.save(
        update_fields=["access_token", "expires_at", "last_error", "updated_at"]
    )
    logger.warning("Threads token cleared: %s", reason)

    try:
        from social.services.comment_notify import notify_staff_text

        notify_staff_text(
            "⚠️ Threads: доступ відкликано.\n"
            "Пости в Threads зупинено. Щоб відновити — заново пройти OAuth "
            "в адмінці (Social → Threads token).",
            video=True,
        )
    except Exception:
        logger.exception("Threads revoke alert could not be delivered")


@csrf_exempt
@require_POST
def threads_deauthorize(request):
    """The account owner removed our app from their Threads profile."""
    try:
        payload = parse_signed_request(
            request.POST.get("signed_request", ""), app_secret()
        )
    except SignedRequestError as exc:
        logger.warning("Threads deauthorize rejected: %s", exc)
        return JsonResponse({"error": "invalid signed_request"}, status=400)

    _forget_token("Користувач відкликав доступ у Threads", str(payload.get("user_id") or ""))
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def threads_data_deletion(request):
    """
    A data-deletion request. Meta expects a status URL and a confirmation code.

    We hold no personal data of Threads users — only our own account's token —
    so honouring this is the same action as a deauthorization, and it completes
    immediately.
    """
    try:
        payload = parse_signed_request(
            request.POST.get("signed_request", ""), app_secret()
        )
    except SignedRequestError as exc:
        logger.warning("Threads data deletion rejected: %s", exc)
        return JsonResponse({"error": "invalid signed_request"}, status=400)

    _forget_token("Запит на видалення даних Threads", str(payload.get("user_id") or ""))

    confirmation_code = secrets.token_hex(8)
    return JsonResponse(
        {
            "url": "https://mrcarpet24.com/api/threads/data-deletion/status/",
            "confirmation_code": confirmation_code,
        }
    )


def threads_data_deletion_status(request):
    """
    Where Meta sends a person to check on their deletion request.

    Always "done": the only thing we ever stored was our own access token, and
    it is cleared synchronously by the request above.
    """
    return JsonResponse(
        {
            "status": "completed",
            "detail": (
                "mrCarpet stores no personal data from Threads users. "
                "The stored access token was deleted immediately."
            ),
        }
    )
