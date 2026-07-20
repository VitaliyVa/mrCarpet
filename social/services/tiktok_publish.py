"""
Daily TikTok publishing pipeline.

    pick -> vertical frame -> clip -> montage -> TikTok -> cleanup -> report

TikTok pulls the file from our own domain rather than receiving an upload, so
the montage has to stay reachable until TikTok says PUBLISH_COMPLETE. Deleting
it earlier — say, right after the API returns a publish_id — leaves TikTok
fetching a 404 and the post silently never appears.

Anything that fails keeps its files: a run that dies at 04:00 should leave
enough behind to diagnose it in the morning.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage

from social.models import SocialSettings, TikTokDailyPick
from social.services import tiktok, tiktok_budget
from social.services.media_urls import site_base
from social.services.tiktok_montage import build_montage, ffmpeg_available
from social.services.tiktok_music import absolute_track_path, pick_track
from social.services.tiktok_rotation import mark_failed, mark_published
from social.services.tiktok_script import build_caption, build_script
from social.services.tiktok_video import generate_video_for_pick

logger = logging.getLogger(__name__)

MONTAGE_DIR = "social/tiktok/final"


class TikTokPipelineError(RuntimeError):
    pass


def _notify(text: str) -> None:
    """Report to the staff chat; never let a notification failure abort a run."""
    try:
        from social.services.comment_notify import notify_staff_text

        notify_staff_text(text)
    except Exception:
        logger.exception("TikTok report could not be delivered")


def _delete(path: str) -> None:
    if not path:
        return
    try:
        if default_storage.exists(path):
            default_storage.delete(path)
    except Exception:
        logger.exception("could not delete %s", path)


def build_final_video(pick: TikTokDailyPick, *, force: bool = False) -> str:
    """
    Produce the montage for a pick and return its storage path.

    The raw clip is generated first (or reused if the pick already has one), so
    a re-run after a publishing failure does not pay for the video twice.
    """
    if not ffmpeg_available():
        raise TikTokPipelineError("ffmpeg is not installed in this environment")

    if not pick.video_path or force:
        generate_video_for_pick(pick, force=force)
        pick.refresh_from_db()

    clip = Path(settings.MEDIA_ROOT) / pick.video_path
    if not clip.exists():
        raise TikTokPipelineError(f"generated clip is missing: {clip}")

    script = build_script(pick)
    track = pick_track(pick.pk)
    relative = f"{MONTAGE_DIR}/pick-{pick.pk}.mp4"
    target = Path(settings.MEDIA_ROOT) / relative
    build_montage(
        str(clip),
        script,
        str(target),
        music_path=absolute_track_path(track) if track else "",
    )
    return relative


def publish_pick(pick: TikTokDailyPick, *, force: bool = False) -> dict:
    """
    Publish a pick to TikTok and clean up once TikTok confirms.

    Returns the TikTok result dict. Raises on any failure, having recorded the
    error on the pick and alerted the staff chat.
    """
    social = SocialSettings.load()
    if not social.tiktok_auto_enabled and not force:
        raise TikTokPipelineError("TikTok auto posting disabled in Social settings")
    if pick.product_id is None:
        raise TikTokPipelineError("Pick has no product")
    if pick.status == TikTokDailyPick.Status.PUBLISHED and not force:
        logger.info("TikTok pick #%s already published", pick.pk)
        return {"already_published": True}

    montage_path = ""
    try:
        script = build_script(pick)
        caption = build_caption(pick, script)
        montage_path = build_final_video(pick, force=force)

        video_url = f"{site_base()}{settings.MEDIA_URL}{montage_path}"
        if not video_url.startswith("https://"):
            raise TikTokPipelineError(
                f"video_url must be public HTTPS for PULL_FROM_URL: {video_url}"
            )

        # Unaudited apps may only post SELF_ONLY, and the account's own list is
        # narrower than the API's constant, so ask rather than assume.
        options = tiktok.creator_privacy_options()
        privacy = "SELF_ONLY" if not tiktok.audit_passed() else (
            "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in options else options[0]
        )

        logger.info("TikTok publish pick=%s privacy=%s url=%s", pick.pk, privacy, video_url)
        result = tiktok.publish_video(
            video_url=video_url,
            caption=caption,
            privacy_level=privacy,
            allow_comment=True,
            # The music is ours and the visuals are generated, so both
            # declarations are honest and required.
            music_usage_confirmed=True,
            made_with_ai=True,
        )
    except Exception as exc:
        mark_failed(pick, str(exc))
        _notify(
            f"❌ TikTok: пост не вийшов\n"
            f"Товар: {pick.product}\n"
            f"Помилка: {str(exc)[:400]}\n"
            f"Файли залишено для розбору."
        )
        raise

    # TikTok has the video now, so the local copies can go.
    _delete(montage_path)
    _delete(pick.video_path)
    pick.video_path = ""
    pick.save(update_fields=["video_path", "updated"])
    mark_published(pick)

    status = tiktok_budget.budget_status()
    _notify(
        f"✅ TikTok: опубліковано\n"
        f"Товар: {pick.product}\n"
        f"{script['price']} · {script['size']}\n"
        f"Приватність: {result.get('privacy')}\n"
        f"Витрачено за місяць: ${status['spent_usd']} з ${status['ceiling_usd']}"
    )
    logger.info("TikTok published pick=%s id=%s", pick.pk, result.get("external_id"))
    return result
