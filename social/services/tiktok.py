"""TikTok Content Posting API (Direct Post)."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from django.conf import settings

from social.models import SocialSettings

logger = logging.getLogger(__name__)

INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
PHOTO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/content/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
HTTP_TIMEOUT = 60
POLL_INTERVAL_SEC = 5
POLL_MAX_ATTEMPTS = 36

ALLOWED_PRIVACY = frozenset(
    {
        "PUBLIC_TO_EVERYONE",
        "MUTUAL_FOLLOW_FRIENDS",
        "FOLLOWER_OF_CREATOR",
        "SELF_ONLY",
    }
)


class TikTokConfigError(RuntimeError):
    pass


class TikTokPublishError(RuntimeError):
    pass


def _access_token() -> str:
    """
    Stored OAuth token, refreshed on demand; env var kept as a legacy fallback.

    Every request in this module goes through _headers(), so refreshing here
    covers publish_video, publish_photos, creator info and status polling.
    """
    from social.services.tiktok_auth import get_valid_access_token

    try:
        token = get_valid_access_token()
    except Exception:
        logger.exception("TikTok token refresh failed")
        token = ""
    if token:
        return token
    return (getattr(settings, "TIKTOK_ACCESS_TOKEN", "") or "").strip()


def _open_id() -> str:
    from social.models import TikTokToken

    try:
        stored = (TikTokToken.load().open_id or "").strip()
    except Exception:
        stored = ""
    return stored or (getattr(settings, "TIKTOK_OPEN_ID", "") or "").strip()


def tiktok_configured() -> bool:
    return bool(_access_token() and _open_id())


def audit_passed() -> bool:
    env_flag = str(getattr(settings, "TIKTOK_AUDIT_PASSED", "false") or "false").lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        return env_flag or bool(SocialSettings.load().tiktok_audit_passed)
    except Exception:
        return env_flag


def _headers() -> dict[str, str]:
    token = _access_token()
    if not token:
        raise TikTokConfigError("TIKTOK_ACCESS_TOKEN empty")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def query_creator_info() -> dict[str, Any]:
    if not tiktok_configured():
        raise TikTokConfigError("TikTok tokens not configured")
    resp = requests.post(
        CREATOR_INFO_URL,
        headers=_headers(),
        json={},
        timeout=HTTP_TIMEOUT,
    )
    # creator_info/query uses empty body with bearer token for the authorized user
    try:
        data = resp.json()
    except ValueError as exc:
        raise TikTokPublishError(f"creator_info invalid JSON: {resp.text[:300]}") from exc
    if resp.status_code >= 400 or data.get("error", {}).get("code") not in (None, "ok", "OK", ""):
        # TikTok returns error.code == "ok" on success in some versions
        err = data.get("error") or data
        if isinstance(err, dict) and str(err.get("code", "")).lower() in ("ok", ""):
            return data.get("data") or data
        if resp.status_code < 400 and str((data.get("error") or {}).get("code", "")).lower() == "ok":
            return data.get("data") or {}
        raise TikTokPublishError(f"creator_info failed: {err}")
    return data.get("data") or data


def _normalize_privacy(requested: str) -> str:
    level = (requested or "").strip()
    if level not in ALLOWED_PRIVACY:
        raise TikTokPublishError(
            "tt_privacy_level must be explicitly set "
            "(PUBLIC_TO_EVERYONE / MUTUAL_FOLLOW_FRIENDS / FOLLOWER_OF_CREATOR / SELF_ONLY)"
        )
    if not audit_passed() and level != "SELF_ONLY":
        # Unaudited clients can only post SELF_ONLY
        logger.warning("TikTok audit not passed — forcing SELF_ONLY (was %s)", level)
        return "SELF_ONLY"
    return level


def publish_video(
    *,
    video_url: str,
    caption: str,
    privacy_level: str,
    allow_comment: bool = True,
    allow_duet: bool = False,
    allow_stitch: bool = False,
    commercial_disclosure: bool = False,
    music_usage_confirmed: bool = False,
) -> dict[str, str]:
    if not tiktok_configured():
        raise TikTokConfigError("TikTok not configured")
    if not video_url.startswith("https://"):
        raise TikTokPublishError("video_url must be public HTTPS (verified domain)")
    if not music_usage_confirmed:
        raise TikTokPublishError("TikTok requires music usage confirmation before publish")

    privacy = _normalize_privacy(privacy_level)
    # Branded content typically forces public — if unaudited, reject branded
    if commercial_disclosure and not audit_passed():
        raise TikTokPublishError(
            "Commercial disclosure requires public posts; wait for TikTok audit"
        )

    payload = {
        "post_info": {
            "title": (caption or "")[:150],
            "privacy_level": privacy,
            "disable_comment": not allow_comment,
            "disable_duet": not allow_duet,
            "disable_stitch": not allow_stitch,
            "video_made_with_ai": False,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }
    if commercial_disclosure:
        payload["post_info"]["brand_content_toggle"] = True
        payload["post_info"]["brand_organic_toggle"] = True

    resp = requests.post(INIT_URL, headers=_headers(), json=payload, timeout=HTTP_TIMEOUT)
    try:
        data = resp.json()
    except ValueError as exc:
        raise TikTokPublishError(f"init invalid JSON: {resp.text[:300]}") from exc

    err = data.get("error") or {}
    if resp.status_code >= 400 or str(err.get("code", "ok")).lower() not in ("ok", ""):
        raise TikTokPublishError(f"TikTok init failed: {data}")

    publish_id = str((data.get("data") or {}).get("publish_id") or "")
    if not publish_id:
        raise TikTokPublishError(f"No publish_id: {data}")

    status_payload = _poll_status(publish_id)
    return _result_from_status(status_payload, publish_id=publish_id, privacy=privacy)


def publish_photos(
    *,
    image_urls: list[str],
    caption: str,
    privacy_level: str,
    allow_comment: bool = True,
    commercial_disclosure: bool = False,
    music_usage_confirmed: bool = False,
    cover_index: int = 0,
) -> dict[str, str]:
    """TikTok photo / slideshow via Content Posting PHOTO + PULL_FROM_URL."""
    if not tiktok_configured():
        raise TikTokConfigError("TikTok not configured")
    urls = [u for u in image_urls if (u or "").startswith("https://")]
    if not urls:
        raise TikTokPublishError("Need at least one public HTTPS image_url")
    if len(urls) > 35:
        raise TikTokPublishError("TikTok photo post supports max 35 images")
    if not music_usage_confirmed:
        raise TikTokPublishError("TikTok requires music usage confirmation before publish")

    privacy = _normalize_privacy(privacy_level)
    if commercial_disclosure and not audit_passed():
        raise TikTokPublishError(
            "Commercial disclosure requires public posts; wait for TikTok audit"
        )

    cover = max(0, min(cover_index, len(urls) - 1))
    title = (caption or "")[:90]
    description = (caption or "")[:4000]
    payload: dict[str, Any] = {
        "media_type": "PHOTO",
        "post_mode": "DIRECT_POST",
        "post_info": {
            "title": title,
            "description": description,
            "privacy_level": privacy,
            "disable_comment": not allow_comment,
            "auto_add_music": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_images": urls,
            "photo_cover_index": cover,
        },
    }
    if commercial_disclosure:
        payload["post_info"]["brand_content_toggle"] = True
        payload["post_info"]["brand_organic_toggle"] = True

    resp = requests.post(
        PHOTO_INIT_URL, headers=_headers(), json=payload, timeout=HTTP_TIMEOUT
    )
    try:
        data = resp.json()
    except ValueError as exc:
        raise TikTokPublishError(f"photo init invalid JSON: {resp.text[:300]}") from exc

    err = data.get("error") or {}
    if resp.status_code >= 400 or str(err.get("code", "ok")).lower() not in ("ok", ""):
        raise TikTokPublishError(f"TikTok photo init failed: {data}")

    publish_id = str((data.get("data") or {}).get("publish_id") or "")
    if not publish_id:
        raise TikTokPublishError(f"No publish_id: {data}")

    status_payload = _poll_status(publish_id)
    return _result_from_status(status_payload, publish_id=publish_id, privacy=privacy)


def _result_from_status(
    status_payload: dict[str, Any], *, publish_id: str, privacy: str
) -> dict[str, str]:
    external_ids = status_payload.get("publicaly_available_post_id") or status_payload.get(
        "publicly_available_post_id"
    )
    # API field name historically misspelled
    post_id = ""
    if isinstance(external_ids, list) and external_ids:
        post_id = str(external_ids[0])
    elif isinstance(external_ids, str):
        post_id = external_ids

    return {
        "external_id": post_id or publish_id,
        "external_url": "",
        "privacy": privacy,
    }


def _poll_status(publish_id: str) -> dict[str, Any]:
    for _ in range(POLL_MAX_ATTEMPTS):
        resp = requests.post(
            STATUS_URL,
            headers=_headers(),
            json={"publish_id": publish_id},
            timeout=HTTP_TIMEOUT,
        )
        try:
            data = resp.json()
        except ValueError:
            time.sleep(POLL_INTERVAL_SEC)
            continue
        body = data.get("data") or {}
        status = (body.get("status") or "").upper()
        if status in ("PUBLISH_COMPLETE", "COMPLETE", "SUCCESS"):
            return body
        if status in ("FAILED", "PUBLISH_FAILED", "ERROR"):
            raise TikTokPublishError(f"TikTok publish failed: {body}")
        time.sleep(POLL_INTERVAL_SEC)
    raise TikTokPublishError(f"TikTok publish timeout publish_id={publish_id}")


def setup_status() -> dict[str, Any]:
    from social.services.tiktok_auth import oauth_configured, token_status

    status = {
        "configured": tiktok_configured(),
        "audit_passed": audit_passed(),
        "open_id_set": bool(_open_id()),
        "client_key_set": bool((getattr(settings, "TIKTOK_CLIENT_KEY", "") or "").strip()),
        "oauth_configured": oauth_configured(),
    }
    try:
        status["token"] = token_status()
    except Exception as exc:  # diagnostics must never raise
        status["token"] = {"error": str(exc)}
    return status
