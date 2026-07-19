"""Meta Graph API — Instagram Reels + Facebook Page video."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_GRAPH_VERSION = "v21.0"
POLL_INTERVAL_SEC = 3
POLL_MAX_ATTEMPTS = 40
HTTP_TIMEOUT = 60


class MetaConfigError(RuntimeError):
    pass


class MetaPublishError(RuntimeError):
    pass


def _graph_version() -> str:
    return (getattr(settings, "META_GRAPH_VERSION", "") or DEFAULT_GRAPH_VERSION).strip()


def _token() -> str:
    return (getattr(settings, "META_PAGE_ACCESS_TOKEN", "") or "").strip()


def _ig_user_id() -> str:
    return (getattr(settings, "META_IG_USER_ID", "") or "").strip()


def _page_id() -> str:
    return (getattr(settings, "META_PAGE_ID", "") or "").strip()


def meta_configured(*, need_ig: bool = False, need_fb: bool = False) -> bool:
    if not _token():
        return False
    if need_ig and not _ig_user_id():
        return False
    if need_fb and not _page_id():
        return False
    return True


def _graph(method: str, path: str, *, params: dict | None = None, data: dict | None = None) -> dict[str, Any]:
    token = _token()
    if not token:
        raise MetaConfigError("META_PAGE_ACCESS_TOKEN empty")
    url = f"https://graph.facebook.com/{_graph_version()}/{path.lstrip('/')}"
    params = dict(params or {})
    params["access_token"] = token
    try:
        if method.upper() == "GET":
            resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        else:
            resp = requests.post(url, params=params, data=data or {}, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise MetaPublishError(f"Meta HTTP error: {exc}") from exc

    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        payload = {"raw": (resp.text or "")[:500]}

    if resp.status_code >= 400 or payload.get("error"):
        err = payload.get("error") or payload
        raise MetaPublishError(f"Meta API {resp.status_code}: {err}")
    return payload


def _wait_container(container_id: str) -> None:
    for _ in range(POLL_MAX_ATTEMPTS):
        data = _graph("GET", container_id, params={"fields": "status_code,status"})
        code = (data.get("status_code") or "").upper()
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise MetaPublishError(f"IG container {container_id} status={code}: {data}")
        time.sleep(POLL_INTERVAL_SEC)
    raise MetaPublishError(f"IG container {container_id} timeout waiting FINISHED")


def publish_instagram_reel(*, video_url: str, caption: str, cover_url: str = "") -> dict[str, str]:
    ig = _ig_user_id()
    if not ig:
        raise MetaConfigError("META_IG_USER_ID empty")
    if not video_url.startswith("https://"):
        raise MetaPublishError("video_url must be public HTTPS for Meta crawl")

    body: dict[str, Any] = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption or "",
        "share_to_feed": "true",
    }
    if cover_url:
        body["cover_url"] = cover_url

    created = _graph("POST", f"{ig}/media", data=body)
    container_id = str(created.get("id") or "")
    if not container_id:
        raise MetaPublishError(f"No container id: {created}")

    _wait_container(container_id)
    published = _graph("POST", f"{ig}/media_publish", data={"creation_id": container_id})
    media_id = str(published.get("id") or container_id)
    return {
        "external_id": media_id,
        "external_url": f"https://www.instagram.com/reel/{media_id}/",
    }


def publish_facebook_page_video(*, video_url: str, caption: str, title: str = "") -> dict[str, str]:
    page = _page_id()
    if not page:
        raise MetaConfigError("META_PAGE_ID empty")
    if not video_url.startswith("https://"):
        raise MetaPublishError("video_url must be public HTTPS")

    body = {
        "file_url": video_url,
        "description": caption or "",
        "published": "true",
    }
    if title:
        body["title"] = title[:255]

    published = _graph("POST", f"{page}/videos", data=body)
    video_id = str(published.get("id") or "")
    if not video_id:
        raise MetaPublishError(f"No FB video id: {published}")
    return {
        "external_id": video_id,
        "external_url": f"https://www.facebook.com/{page}/videos/{video_id}/",
    }


def setup_status() -> dict[str, Any]:
    return {
        "token_set": bool(_token()),
        "ig_user_id": _ig_user_id() or None,
        "page_id": _page_id() or None,
        "graph_version": _graph_version(),
        "ig_ready": meta_configured(need_ig=True),
        "fb_ready": meta_configured(need_fb=True),
    }
