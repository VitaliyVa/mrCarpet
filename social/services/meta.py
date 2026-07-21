"""Meta Graph API — Instagram Reels/photos + Facebook Page video/photos."""

from __future__ import annotations

import json
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


def publish_instagram_reel(
    *,
    video_url: str,
    caption: str,
    cover_url: str = "",
    thumb_offset_ms: int | None = None,
) -> dict[str, str]:
    ig = _ig_user_id()
    if not ig:
        raise MetaConfigError("META_IG_USER_ID empty")
    if not video_url.startswith("https://"):
        raise MetaPublishError("video_url must be public HTTPS for Meta crawl")

    body: dict[str, Any] = {
        "media_type": "REELS",
        "video_url": video_url,
        # Reels tab *and* the main feed. Without it the reel only appears in
        # the Reels tab, which halves the surfaces it can be found on.
        "share_to_feed": "true",
        "caption": caption or "",
    }
    if cover_url:
        body["cover_url"] = cover_url
    elif thumb_offset_ms is not None:
        # Frame zero is the empty room before the question fades in — a blank
        # thumbnail in the grid. We already pick a better moment for TikTok;
        # Instagram was defaulting to zero because nobody told it otherwise.
        body["thumb_offset"] = int(thumb_offset_ms)

    created = _graph("POST", f"{ig}/media", data=body)
    container_id = str(created.get("id") or "")
    if not container_id:
        raise MetaPublishError(f"No container id: {created}")

    _wait_container(container_id)
    published = _graph("POST", f"{ig}/media_publish", data={"creation_id": container_id})
    media_id = str(published.get("id") or container_id)
    return {
        "external_id": media_id,
        "external_url": _instagram_permalink(media_id),
    }


def _instagram_permalink(media_id: str) -> str:
    """
    Ask Instagram for the public URL instead of building one.

    The public path uses a shortcode (…/reel/DbDTARpjSQJ/), which has nothing
    to do with the numeric media id the API returns. Assembling the URL from
    the id produces a link that looks right and 404s.

    Best-effort: a missing permalink is a broken link in a report, not a
    reason to treat a successful publish as failed.
    """
    try:
        data = _graph("GET", media_id, params={"fields": "permalink"})
        permalink = (data.get("permalink") or "").strip()
        if permalink:
            return permalink
    except Exception:
        logger.info("IG permalink lookup failed for %s", media_id)
    return ""


def instagram_media_metrics(media_id: str) -> dict[str, int | None]:
    """
    Likes and comments for a Reel, from the ordinary media fields.

    Views are absent and that is not an oversight: /insights needs
    instagram_manage_insights, which this token does not carry (verified — the
    call returns "(#10) Application does not have permission"). Rather than ask
    a human to walk through a consent screen for one number, the two counters
    that *are* free are collected and views is reported as unknown.

    None means "not reported", never zero — see VideoMetric.
    """
    data = _graph("GET", media_id, params={"fields": "like_count,comments_count"})
    return {
        "views": None,
        "likes": data.get("like_count"),
        "comments": data.get("comments_count"),
    }


def facebook_video_metrics(video_id: str) -> dict[str, int | None]:
    """
    Views, likes and comments for a Reel.

    Uses the video object's own fields rather than /video_insights, which
    needs read_insights that this token lacks. The plain `views` field returns
    the same play count and costs no extra permission.
    """
    data = _graph(
        "GET",
        video_id,
        params={"fields": "views,likes.summary(true),comments.summary(true)"},
    )
    return {
        "views": data.get("views"),
        "likes": ((data.get("likes") or {}).get("summary") or {}).get("total_count"),
        "comments": ((data.get("comments") or {}).get("summary") or {}).get("total_count"),
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


RUPLOAD_URL = "https://rupload.facebook.com/video-upload"


def publish_facebook_reel(
    *, video_url: str, caption: str, title: str = ""
) -> dict[str, str]:
    """
    Post a real Reel to the Page, in three phases.

    Preferred over publish_facebook_page_video for the daily vertical video:
    `/{page}/videos` with `file_url` still works but is not in the current
    docs, and it produces a plain video post rather than a Reel.

    The middle phase looks like a binary upload but is not: passing the file
    location as a `file_url` *header* makes Meta fetch it themselves, which is
    what lets us keep serving the montage from our own domain.

    That fetch arrives as `facebookexternalhit/1.1` — any User-Agent filtering
    in front of the media directory breaks this with a distinctly unhelpful
    error, so leave it reachable.
    """
    page = _page_id()
    token = _token()
    if not page:
        raise MetaConfigError("META_PAGE_ID empty")
    if not token:
        raise MetaConfigError("META_PAGE_ACCESS_TOKEN empty")
    if not video_url.startswith("https://"):
        raise MetaPublishError("video_url must be public HTTPS")

    started = _graph("POST", f"{page}/video_reels", data={"upload_phase": "start"})
    video_id = str(started.get("video_id") or "")
    if not video_id:
        raise MetaPublishError(f"No FB reel video_id: {started}")

    try:
        resp = requests.post(
            f"{RUPLOAD_URL}/{_graph_version()}/{video_id}",
            headers={
                "Authorization": f"OAuth {token}",
                "file_url": video_url,
            },
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise MetaPublishError(f"FB reel upload HTTP error: {exc}") from exc

    try:
        uploaded = resp.json() if resp.content else {}
    except ValueError:
        uploaded = {"raw": (resp.text or "")[:500]}
    if resp.status_code >= 400 or uploaded.get("error"):
        raise MetaPublishError(f"FB reel upload {resp.status_code}: {uploaded}")

    body = {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": "PUBLISHED",
        "description": caption or "",
        # feed_targeting, deliberately not targeting: the first prioritises an
        # audience, the second *restricts* who may see the post at all. We want
        # Ukrainians shown it first, not everyone else locked out — a rug ships
        # to whoever wants it.
        "feed_targeting": json.dumps({"geo_locations": {"countries": ["UA"]}}),
    }
    if title:
        body["title"] = title[:255]
    _graph("POST", f"{page}/video_reels", data=body)

    # Comments are reported against the post id, not the video id, so resolve
    # it now while we know what we just published. Best-effort: failing to
    # learn it costs comment routing, not the post.
    post_id = ""
    try:
        post_id = str(
            (_graph("GET", video_id, params={"fields": "post_id"}) or {}).get("post_id")
            or ""
        )
    except Exception:
        logger.info("FB reel post_id lookup failed video_id=%s", video_id)

    return {
        "external_id": video_id,
        "post_id": post_id,
        "external_url": f"https://www.facebook.com/reel/{video_id}/",
    }


def publish_instagram_photos(*, image_urls: list[str], caption: str) -> dict[str, str]:
    """Single IMAGE or CAROUSEL (2–10) via Graph Content Publishing."""
    ig = _ig_user_id()
    if not ig:
        raise MetaConfigError("META_IG_USER_ID empty")
    urls = [u for u in image_urls if (u or "").startswith("https://")]
    if not urls:
        raise MetaPublishError("Need at least one public HTTPS image_url")
    if len(urls) > 10:
        raise MetaPublishError("Instagram carousel supports max 10 images")

    if len(urls) == 1:
        created = _graph(
            "POST",
            f"{ig}/media",
            data={"image_url": urls[0], "caption": caption or ""},
        )
        container_id = str(created.get("id") or "")
        if not container_id:
            raise MetaPublishError(f"No IG image container: {created}")
        _wait_container(container_id)
        published = _graph(
            "POST", f"{ig}/media_publish", data={"creation_id": container_id}
        )
        media_id = str(published.get("id") or container_id)
        return {
            "external_id": media_id,
            "external_url": f"https://www.instagram.com/p/{media_id}/",
        }

    child_ids: list[str] = []
    for url in urls:
        child = _graph(
            "POST",
            f"{ig}/media",
            data={"image_url": url, "is_carousel_item": "true"},
        )
        cid = str(child.get("id") or "")
        if not cid:
            raise MetaPublishError(f"No IG carousel child: {child}")
        _wait_container(cid)
        child_ids.append(cid)

    parent = _graph(
        "POST",
        f"{ig}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption or "",
        },
    )
    parent_id = str(parent.get("id") or "")
    if not parent_id:
        raise MetaPublishError(f"No IG carousel container: {parent}")
    _wait_container(parent_id)
    published = _graph(
        "POST", f"{ig}/media_publish", data={"creation_id": parent_id}
    )
    media_id = str(published.get("id") or parent_id)
    return {
        "external_id": media_id,
        "external_url": f"https://www.instagram.com/p/{media_id}/",
    }


def publish_facebook_page_photos(*, image_urls: list[str], caption: str) -> dict[str, str]:
    """One photo or multi-photo feed post via unpublished photos + attached_media."""
    page = _page_id()
    if not page:
        raise MetaConfigError("META_PAGE_ID empty")
    urls = [u for u in image_urls if (u or "").startswith("https://")]
    if not urls:
        raise MetaPublishError("Need at least one public HTTPS image_url")

    if len(urls) == 1:
        published = _graph(
            "POST",
            f"{page}/photos",
            data={
                "url": urls[0],
                "caption": caption or "",
                "published": "true",
            },
        )
        photo_id = str(published.get("id") or published.get("post_id") or "")
        if not photo_id:
            raise MetaPublishError(f"No FB photo id: {published}")
        return {
            "external_id": photo_id,
            "external_url": f"https://www.facebook.com/{page}/photos/{photo_id}/",
        }

    media_fbids: list[str] = []
    for url in urls:
        unpublished = _graph(
            "POST",
            f"{page}/photos",
            data={"url": url, "published": "false"},
        )
        fid = str(unpublished.get("id") or "")
        if not fid:
            raise MetaPublishError(f"No unpublished FB photo id: {unpublished}")
        media_fbids.append(fid)

    # Graph accepts attached_media[0]=… form fields
    data: dict[str, Any] = {"message": caption or ""}
    for i, fid in enumerate(media_fbids):
        data[f"attached_media[{i}]"] = f'{{"media_fbid":"{fid}"}}'

    published = _graph("POST", f"{page}/feed", data=data)
    post_id = str(published.get("id") or "")
    if not post_id:
        raise MetaPublishError(f"No FB feed post id: {published}")
    return {
        "external_id": post_id,
        "external_url": f"https://www.facebook.com/{post_id}",
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
