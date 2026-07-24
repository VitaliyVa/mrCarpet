"""
Buffer GraphQL client — the supported route for posting to TikTok.

TikTok's Content Posting API only grants production access to apps that serve
third-party creators; a single brand posting to its own account is "personal or
internal company use", which TikTok rejects (our own Direct Post audit was
declined on exactly that ground). Buffer already holds an audited TikTok app, so
we hand it a public video URL and it publishes on our behalf — no audit of ours.

One endpoint, one mutation. The whole surface we need is:

    query  account.organizations       -> organization id
    query  channels(organizationId)     -> the TikTok channel id
    mutation createPost(channelId, ...)  -> queue a video for that channel

Media is a public HTTPS URL, never an upload — the same shape TikTok's
PULL_FROM_URL wanted, so the pipeline's existing `video_url` is reused as-is and
the montage must stay reachable until Buffer publishes it (see cleanup_old_media).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_URL = "https://api.buffer.com"
HTTP_TIMEOUT = 60
TIKTOK_SERVICE = "tiktok"

# Resolved once per process: neither the org nor the channel changes between
# posts, and each lookup is a network round-trip we would otherwise pay on every
# publish. Cleared implicitly on restart, which is often enough.
_org_id_cache: str = ""
_channel_id_cache: str = ""


class BufferConfigError(RuntimeError):
    pass


class BufferPublishError(RuntimeError):
    pass


def _api_key() -> str:
    return (getattr(settings, "BUFFER_API_KEY", "") or "").strip()


def buffer_configured() -> bool:
    return bool(_api_key())


def _headers() -> dict[str, str]:
    key = _api_key()
    if not key:
        raise BufferConfigError("BUFFER_API_KEY empty")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _graphql(query: str) -> dict[str, Any]:
    """
    Run one GraphQL document and return its `data`.

    Buffer reports failure two ways and both must raise: a transport/validation
    problem lands in a top-level `errors` array, while a rejected mutation comes
    back as a `MutationError` union member inside `data` — the caller unwraps the
    latter because only it knows which field held the payload.
    """
    resp = requests.post(
        API_URL,
        headers=_headers(),
        data=json.dumps({"query": query}),
        timeout=HTTP_TIMEOUT,
    )
    try:
        body = resp.json()
    except ValueError as exc:
        raise BufferPublishError(
            f"Buffer returned non-JSON ({resp.status_code}): {resp.text[:300]}"
        ) from exc

    if body.get("errors"):
        raise BufferPublishError(f"Buffer GraphQL error: {body['errors']}")
    if resp.status_code >= 400:
        raise BufferPublishError(f"Buffer HTTP {resp.status_code}: {body}")

    data = body.get("data")
    if not isinstance(data, dict):
        raise BufferPublishError(f"Buffer response without data: {body}")
    return data


def _gql_str(value: str) -> str:
    """
    A GraphQL string literal for `value`.

    A GraphQL string literal is a JSON string, so json.dumps produces a safe one
    — quotes, backslashes, newlines and emoji in a caption all get escaped rather
    than breaking the document. This is why the mutation is built inline instead
    of interpolated by hand.
    """
    return json.dumps(str(value))


def organization_id() -> str:
    """The account's organization id — configured value wins, else first found."""
    global _org_id_cache
    override = (getattr(settings, "BUFFER_ORG_ID", "") or "").strip()
    if override:
        return override
    if _org_id_cache:
        return _org_id_cache

    data = _graphql("query { account { organizations { id } } }")
    orgs = ((data.get("account") or {}).get("organizations")) or []
    if not orgs:
        raise BufferConfigError("Buffer account has no organizations")
    _org_id_cache = str(orgs[0].get("id") or "")
    if not _org_id_cache:
        raise BufferConfigError("Buffer organization has no id")
    return _org_id_cache


def list_channels() -> list[dict[str, Any]]:
    """Every connected channel for the org — used by publish and by diagnostics."""
    org = organization_id()
    query = (
        "query { channels(input: { organizationId: "
        + _gql_str(org)
        + " }) { id name displayName service isQueuePaused } }"
    )
    data = _graphql(query)
    channels = data.get("channels")
    return channels if isinstance(channels, list) else []


def tiktok_channel_id() -> str:
    """
    The connected TikTok channel's id — configured value wins, else discovered.

    A blank result is a setup problem (no TikTok channel connected in Buffer),
    not a transient one, so it raises with a message the daily report can show.
    """
    global _channel_id_cache
    override = (getattr(settings, "BUFFER_TIKTOK_CHANNEL_ID", "") or "").strip()
    if override:
        return override
    if _channel_id_cache:
        return _channel_id_cache

    for channel in list_channels():
        if str(channel.get("service") or "").lower() == TIKTOK_SERVICE:
            _channel_id_cache = str(channel.get("id") or "")
            if _channel_id_cache:
                return _channel_id_cache
    raise BufferConfigError(
        "No TikTok channel connected in Buffer — connect @mrcarpet24 in the Buffer app"
    )


def publish_video(
    *,
    video_url: str,
    caption: str,
    cover_timestamp_ms: int | None = None,
) -> dict[str, str]:
    """
    Queue a video to the TikTok channel and return the created Buffer post id.

    The post lands in Buffer's queue (mode addToQueue) and Buffer publishes it at
    the channel's next slot, so there is no live TikTok url to return yet — the
    id here is Buffer's, enough to reconcile against the daily report.
    """
    if not buffer_configured():
        raise BufferConfigError("Buffer not configured")
    if not video_url.startswith("https://"):
        raise BufferPublishError(f"video_url must be public HTTPS: {video_url}")

    channel_id = tiktok_channel_id()

    metadata = ""
    if cover_timestamp_ms is not None:
        # Frame zero of our montage is the bare room before the question fades
        # in — a blank-looking thumbnail. Same offset TikTok's cover used.
        metadata = " metadata: { thumbnailOffset: " + str(int(cover_timestamp_ms)) + " }"

    mutation = (
        "mutation { createPost(input: { "
        "text: " + _gql_str(caption) + " "
        "channelId: " + _gql_str(channel_id) + " "
        "schedulingType: automatic "
        "mode: addToQueue "
        "assets: [{ video: { url: " + _gql_str(video_url) + metadata + " } }] "
        "}) { "
        "... on PostActionSuccess { post { id text } } "
        "... on MutationError { message } "
        "} }"
    )

    data = _graphql(mutation)
    result = data.get("createPost") or {}
    if result.get("message") and not result.get("post"):
        raise BufferPublishError(f"Buffer rejected the post: {result['message']}")

    post = result.get("post") or {}
    post_id = str(post.get("id") or "")
    if not post_id:
        raise BufferPublishError(f"Buffer createPost returned no post id: {data}")

    return {"external_id": post_id, "external_url": ""}


def setup_status() -> dict[str, Any]:
    """Diagnostics for the admin: key present, org, and the TikTok channel."""
    status: dict[str, Any] = {
        "configured": buffer_configured(),
        "api_key_set": bool(_api_key()),
    }
    if not status["configured"]:
        return status
    try:
        status["organization_id"] = organization_id()
        status["channels"] = [
            {"service": c.get("service"), "name": c.get("displayName") or c.get("name")}
            for c in list_channels()
        ]
        status["tiktok_channel_id"] = tiktok_channel_id()
    except Exception as exc:  # diagnostics must never raise
        status["error"] = str(exc)
    return status
