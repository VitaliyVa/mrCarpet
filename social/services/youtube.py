"""
YouTube Shorts publishing — resumable upload of the daily video.

The odd one out among our networks: everyone else fetches the montage from
our own HTTPS domain, YouTube wants the bytes. That is why the adapter
contract carries `needs_local_file` and why the montage is no longer deleted
the moment the first network confirms.

There is no Shorts endpoint. YouTube classifies a video as a Short from the
file itself — vertical and under three minutes — so `videos.insert` is the
whole API surface.

**Until the compliance audit passes every upload comes back private.** Not an
error, and not something the code can detect from the response: the API
answers 200 and quietly rewrites privacyStatus. The response is checked
against what we asked for so the report tells the truth.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from social.models import YouTubeToken
from social.services.youtube_auth import get_valid_access_token

logger = logging.getLogger(__name__)

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
API = "https://www.googleapis.com/youtube/v3"
HTTP_TIMEOUT = 60
UPLOAD_TIMEOUT = 600

# 22 = People & Blogs. Retail product clips have no better fit, and the
# category mainly affects browse surfaces rather than Shorts distribution.
CATEGORY_ID = "22"

# YouTube expects an explicit answer; silence is treated as undeclared.
MADE_FOR_KIDS = False

# The visuals are model-generated, so this is declared for the same reason we
# set is_aigc on TikTok. Marked here because the field name is the one part of
# the payload not confirmed against a live upload yet — if the first attempt
# returns 400 on an unknown field, drop it and disclose in the description.
DECLARE_SYNTHETIC_MEDIA = True

MAX_TITLE = 100
MAX_DESCRIPTION = 5000


class YouTubeConfigError(RuntimeError):
    pass


class YouTubePublishError(RuntimeError):
    pass


def youtube_configured() -> bool:
    return bool(YouTubeToken.load().is_authorized)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _body(*, title: str, description: str, tags: list[str], privacy: str) -> dict[str, Any]:
    snippet: dict[str, Any] = {
        "title": (title or "")[:MAX_TITLE],
        "description": (description or "")[:MAX_DESCRIPTION],
        "categoryId": CATEGORY_ID,
    }
    if tags:
        snippet["tags"] = tags[:15]

    status: dict[str, Any] = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": MADE_FOR_KIDS,
    }
    if DECLARE_SYNTHETIC_MEDIA:
        status["containsSyntheticMedia"] = True

    return {"snippet": snippet, "status": status}


def upload_video(
    *,
    file_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy: str = "public",
) -> dict[str, str]:
    """
    Upload one video and return its id, URL and the privacy actually applied.

    Two-step resumable upload: a session request that carries the metadata and
    returns a one-off upload URL, then the bytes. Resumable rather than
    multipart because a dropped connection on a mobile-sized file is a real
    event on a small droplet, and this is the shape that can be retried.
    """
    if not youtube_configured():
        raise YouTubeConfigError("YouTube is not authorized — run the OAuth flow")
    if not os.path.exists(file_path):
        raise YouTubePublishError(f"video file is missing: {file_path}")

    token = get_valid_access_token()
    if not token:
        raise YouTubeConfigError("No usable YouTube access token")

    size = os.path.getsize(file_path)
    body = _body(title=title, description=description, tags=tags or [], privacy=privacy)

    try:
        start = requests.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                **_headers(token),
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(size),
                "X-Upload-Content-Type": "video/mp4",
            },
            data=json.dumps(body).encode("utf-8"),
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise YouTubePublishError(f"YouTube session HTTP error: {exc}") from exc

    if start.status_code >= 400:
        raise YouTubePublishError(
            f"YouTube session failed {start.status_code}: {start.text[:400]}"
        )

    session_url = start.headers.get("Location") or start.headers.get("location") or ""
    if not session_url:
        raise YouTubePublishError(f"YouTube returned no upload URL: {start.text[:300]}")

    try:
        with open(file_path, "rb") as handle:
            uploaded = requests.put(
                session_url,
                data=handle,
                headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
                timeout=UPLOAD_TIMEOUT,
            )
    except requests.RequestException as exc:
        raise YouTubePublishError(f"YouTube upload HTTP error: {exc}") from exc

    if uploaded.status_code >= 400:
        raise YouTubePublishError(
            f"YouTube upload failed {uploaded.status_code}: {uploaded.text[:400]}"
        )

    try:
        data = uploaded.json() if uploaded.content else {}
    except ValueError:
        data = {}

    video_id = str(data.get("id") or "")
    if not video_id:
        raise YouTubePublishError(f"YouTube returned no video id: {uploaded.text[:300]}")

    applied = str((data.get("status") or {}).get("privacyStatus") or "")
    if applied and applied != privacy:
        # Expected before the compliance audit clears. Logged rather than
        # raised: the upload did succeed, it is just not visible to anyone.
        logger.warning(
            "YouTube forced privacy %s -> %s (compliance audit not passed?)",
            privacy,
            applied,
        )

    return {
        "external_id": video_id,
        "external_url": f"https://www.youtube.com/shorts/{video_id}",
        "privacy": applied or privacy,
        "forced_private": bool(applied and applied != privacy),
    }


def setup_status() -> dict[str, Any]:
    from social.services.youtube_auth import token_status

    status = token_status()
    status["ready"] = youtube_configured()
    return status
