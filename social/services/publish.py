"""Orchestrate SocialPost → platform deliveries."""

from __future__ import annotations

import logging
import threading
from typing import Iterable

from django.db import close_old_connections, transaction
from django.utils import timezone

from social.models import SocialDelivery, SocialPost
from social.services import meta, tiktok
from social.services.media_urls import absolute_media_url, build_caption

logger = logging.getLogger(__name__)


def validate_post_for_publish(post: SocialPost) -> str:
    """Return error message or empty string if OK to queue."""
    if not any(
        (post.target_instagram, post.target_facebook, post.target_tiktok)
    ):
        return "No target platforms selected"

    kind = post.media_kind or SocialPost.MediaKind.VIDEO
    if kind == SocialPost.MediaKind.VIDEO:
        if not post.video:
            return "No video file"
    elif kind == SocialPost.MediaKind.PHOTOS:
        count = post.images.count()
        if count < 1:
            return "Add at least one gallery image"
        if count > 10:
            return "Max 10 images for gallery posts"
    else:
        return f"Unknown media_kind={kind}"

    if post.target_tiktok:
        if not (post.tt_privacy_level or "").strip():
            return "set TikTok privacy level"
        if not post.tt_music_usage_confirmed:
            return "confirm TikTok music usage"
    return ""


def enqueue_publish(post_id: int) -> None:
    """Queue deliveries and run publish in a background thread."""

    def _run():
        close_old_connections()
        try:
            publish_post(post_id)
        except Exception:
            logger.exception("social publish failed post_id=%s", post_id)
        finally:
            close_old_connections()

    def _schedule():
        threading.Thread(target=_run, daemon=True).start()

    transaction.on_commit(_schedule)


def ensure_deliveries(post: SocialPost) -> list[SocialDelivery]:
    wanted: list[tuple[str, bool]] = [
        (SocialDelivery.Platform.INSTAGRAM, post.target_instagram),
        (SocialDelivery.Platform.FACEBOOK, post.target_facebook),
        (SocialDelivery.Platform.TIKTOK, post.target_tiktok),
    ]
    out: list[SocialDelivery] = []
    for platform, enabled in wanted:
        if not enabled:
            continue
        delivery, _ = SocialDelivery.objects.get_or_create(
            post=post,
            platform=platform,
            defaults={"status": SocialDelivery.Status.QUEUED},
        )
        if delivery.status in (
            SocialDelivery.Status.FAILED,
            SocialDelivery.Status.QUEUED,
        ):
            delivery.status = SocialDelivery.Status.QUEUED
            delivery.error = ""
            delivery.save(update_fields=["status", "error", "updated"])
        out.append(delivery)
    return out


def _image_urls(post: SocialPost) -> list[str]:
    urls: list[str] = []
    for img in post.ordered_images():
        if not img.image:
            continue
        url = absolute_media_url(img.image)
        if url.startswith("https://"):
            urls.append(url)
    return urls


def publish_post(post_id: int) -> SocialPost:
    close_old_connections()
    post = (
        SocialPost.objects.select_related("product")
        .prefetch_related("deliveries", "images")
        .filter(pk=post_id)
        .first()
    )
    if not post:
        raise ValueError(f"SocialPost {post_id} not found")

    err = validate_post_for_publish(post)
    if err:
        post.status = SocialPost.Status.FAILED
        post.last_error = err
        post.save(update_fields=["status", "last_error", "updated"])
        return post

    kind = post.media_kind or SocialPost.MediaKind.VIDEO
    video_url = absolute_media_url(post.video) if post.video else ""
    cover_url = absolute_media_url(post.cover) if post.cover else ""
    image_urls = _image_urls(post) if kind == SocialPost.MediaKind.PHOTOS else []

    deliveries = ensure_deliveries(post)
    post.status = SocialPost.Status.PUBLISHING
    post.last_error = ""
    post.save(update_fields=["status", "last_error", "updated"])

    ok = 0
    fail = 0
    for delivery in deliveries:
        if delivery.status == SocialDelivery.Status.PUBLISHED:
            ok += 1
            continue
        try:
            delivery.status = SocialDelivery.Status.UPLOADING
            delivery.save(update_fields=["status", "updated"])
            _publish_one(
                post,
                delivery,
                kind=kind,
                video_url=video_url,
                cover_url=cover_url,
                image_urls=image_urls,
            )
            if delivery.status in (
                SocialDelivery.Status.PUBLISHED,
                SocialDelivery.Status.PUBLISHED_PRIVATE,
            ):
                ok += 1
            elif delivery.status == SocialDelivery.Status.FAILED:
                fail += 1
        except Exception as exc:
            logger.exception("delivery failed %s", delivery.pk)
            delivery.mark(SocialDelivery.Status.FAILED, error=str(exc))
            fail += 1

    if ok and not fail:
        post.status = SocialPost.Status.PUBLISHED
        post.published_at = timezone.now()
    elif ok and fail:
        post.status = SocialPost.Status.PARTIAL
        post.published_at = timezone.now()
    elif fail:
        post.status = SocialPost.Status.FAILED
        post.last_error = "; ".join(
            d.error for d in post.deliveries.all() if d.error
        )[:2000]
    else:
        post.status = SocialPost.Status.DRAFT
        post.last_error = "No target platforms selected"
    post.save(
        update_fields=["status", "published_at", "last_error", "updated"]
    )
    return post


def _publish_one(
    post: SocialPost,
    delivery: SocialDelivery,
    *,
    kind: str,
    video_url: str,
    cover_url: str,
    image_urls: list[str],
) -> None:
    platform = delivery.platform
    caption = build_caption(post, platform)
    is_photos = kind == SocialPost.MediaKind.PHOTOS

    if platform == SocialDelivery.Platform.INSTAGRAM:
        if not meta.meta_configured(need_ig=True):
            delivery.mark(
                SocialDelivery.Status.FAILED,
                error="Meta IG not configured (META_PAGE_ACCESS_TOKEN / META_IG_USER_ID)",
            )
            return
        if is_photos:
            result = meta.publish_instagram_photos(
                image_urls=image_urls, caption=caption
            )
        else:
            result = meta.publish_instagram_reel(
                video_url=video_url, caption=caption, cover_url=cover_url
            )
        delivery.mark(
            SocialDelivery.Status.PUBLISHED,
            external_id=result.get("external_id", ""),
            external_url=result.get("external_url", ""),
        )
        return

    if platform == SocialDelivery.Platform.FACEBOOK:
        if not meta.meta_configured(need_fb=True):
            delivery.mark(
                SocialDelivery.Status.FAILED,
                error="Meta FB not configured (META_PAGE_ACCESS_TOKEN / META_PAGE_ID)",
            )
            return
        if is_photos:
            result = meta.publish_facebook_page_photos(
                image_urls=image_urls, caption=caption
            )
        else:
            title = post.product.title if post.product_id else "mr.Carpet"
            result = meta.publish_facebook_page_video(
                video_url=video_url, caption=caption, title=title
            )
        delivery.mark(
            SocialDelivery.Status.PUBLISHED,
            external_id=result.get("external_id", ""),
            external_url=result.get("external_url", ""),
        )
        return

    if platform == SocialDelivery.Platform.TIKTOK:
        if not tiktok.tiktok_configured():
            delivery.mark(
                SocialDelivery.Status.FAILED,
                error="TikTok not configured (TIKTOK_ACCESS_TOKEN / TIKTOK_OPEN_ID)",
            )
            return
        if is_photos:
            result = tiktok.publish_photos(
                image_urls=image_urls,
                caption=caption,
                privacy_level=post.tt_privacy_level,
                allow_comment=post.tt_allow_comment,
                commercial_disclosure=post.tt_commercial_disclosure,
                music_usage_confirmed=post.tt_music_usage_confirmed,
            )
        else:
            result = tiktok.publish_video(
                video_url=video_url,
                caption=caption,
                privacy_level=post.tt_privacy_level,
                allow_comment=post.tt_allow_comment,
                allow_duet=post.tt_allow_duet,
                allow_stitch=post.tt_allow_stitch,
                commercial_disclosure=post.tt_commercial_disclosure,
                music_usage_confirmed=post.tt_music_usage_confirmed,
            )
        privacy = result.get("privacy") or post.tt_privacy_level
        status = (
            SocialDelivery.Status.PUBLISHED_PRIVATE
            if privacy == "SELF_ONLY" or not tiktok.audit_passed()
            else SocialDelivery.Status.PUBLISHED
        )
        delivery.mark(
            status,
            external_id=result.get("external_id", ""),
            external_url=result.get("external_url", ""),
        )
        return

    delivery.mark(SocialDelivery.Status.SKIPPED, error=f"Unknown platform {platform}")


def selected_platforms(post: SocialPost) -> Iterable[str]:
    if post.target_instagram:
        yield "instagram"
    if post.target_facebook:
        yield "facebook"
    if post.target_tiktok:
        yield "tiktok"
