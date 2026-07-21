"""
Threads publishing — video posts via the container flow.

Same shape as Instagram: create a media container, wait for Meta to fetch and
process the file, then publish it. The file is always pulled from a public
HTTPS URL; Threads has no upload endpoint at all, so the montage must stay
reachable for the whole processing window.

Unlike TikTok there is no audit gate: posts from an account with a role on the
app are public from the first one.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from social.models import ThreadsToken
from social.services.threads_auth import GRAPH, get_valid_access_token

logger = logging.getLogger(__name__)

API = f"{GRAPH}/v1.0"
HTTP_TIMEOUT = 60

# Meta's own guidance: poll about once a minute, give up after five. Our clips
# are ~12 seconds long, so in practice the first or second check succeeds.
POLL_INTERVAL_SEC = 10
POLL_MAX_ATTEMPTS = 30

TEXT_LIMIT = 500


class ThreadsConfigError(RuntimeError):
    pass


class ThreadsPublishError(RuntimeError):
    pass


def threads_configured() -> bool:
    token = ThreadsToken.load()
    return bool(token.is_authorized and not token.expired)


def _call(method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    token = get_valid_access_token()
    if not token:
        raise ThreadsConfigError("Threads is not authorized — run the OAuth flow")
    params = dict(params)
    params["access_token"] = token
    url = f"{API}/{path.lstrip('/')}"
    try:
        if method.upper() == "GET":
            resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        else:
            resp = requests.post(url, data=params, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise ThreadsPublishError(f"Threads HTTP error: {exc}") from exc

    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {"raw": (resp.text or "")[:500]}
    if resp.status_code >= 400 or data.get("error"):
        err = data.get("error") or data
        raise ThreadsPublishError(f"Threads API {resp.status_code}: {err}")
    return data


def _wait_container(container_id: str) -> None:
    """
    Block until Meta has fetched and processed the video.

    Publishing an unfinished container fails, and the container itself expires
    after 24 hours, so there is no value in waiting longer than the poll budget.
    """
    for _ in range(POLL_MAX_ATTEMPTS):
        data = _call("GET", container_id, {"fields": "status,error_message"})
        status = (data.get("status") or "").upper()
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise ThreadsPublishError(
                f"Threads container {container_id} status={status}: "
                f"{data.get('error_message') or data}"
            )
        time.sleep(POLL_INTERVAL_SEC)
    raise ThreadsPublishError(f"Threads container {container_id} timeout")


def publish_video(*, video_url: str, text: str, topic_tag: str = "") -> dict[str, str]:
    """Post a video to Threads and return its id and permalink."""
    token = ThreadsToken.load()
    if not token.is_authorized:
        raise ThreadsConfigError("Threads is not authorized")
    if not video_url.startswith("https://"):
        raise ThreadsPublishError("video_url must be public HTTPS — Threads pulls it")

    params = {
        "media_type": "VIDEO",
        "video_url": video_url,
        "text": (text or "")[:TEXT_LIMIT],
    }
    # One tag per post, and its own parameter: Meta keeps inline "#" working
    # only for backwards compatibility and says so in the docs.
    if topic_tag:
        params["topic_tag"] = topic_tag[:50]

    created = _call("POST", f"{token.user_id}/threads", params)
    container_id = str(created.get("id") or "")
    if not container_id:
        raise ThreadsPublishError(f"No Threads container id: {created}")

    _wait_container(container_id)

    published = _call(
        "POST",
        f"{token.user_id}/threads_publish",
        {"creation_id": container_id},
    )
    post_id = str(published.get("id") or container_id)

    permalink = ""
    try:
        info = _call("GET", post_id, {"fields": "permalink"})
        permalink = (info.get("permalink") or "").strip()
    except Exception:
        logger.info("Threads permalink fetch failed id=%s", post_id)

    return {
        "external_id": post_id,
        "external_url": permalink or f"https://www.threads.net/@{token.username}",
    }


def setup_status() -> dict[str, Any]:
    from social.services.threads_auth import oauth_configured, token_status

    status = token_status()
    status["oauth_configured"] = oauth_configured()
    status["ready"] = threads_configured()
    return status
