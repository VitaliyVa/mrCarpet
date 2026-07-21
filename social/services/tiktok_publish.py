"""
Daily video pipeline: one montage, several networks.

    pick -> vertical frame -> clip -> montage -> [networks] -> report
                                                      |
                                    files cleaned up a day later, not here

The networks live in `video_networks`; this module knows only that they exist,
that each gets its own delivery row, and that one of them failing must not take
the others down with it.

Two rules earned the hard way:

* **Files outlive the publish.** Meta and Threads fetch the montage
  asynchronously — the container is still being processed after their API has
  already returned an id — and YouTube uploads the bytes rather than fetching a
  URL. Deleting the file when the first network confirms leaves the rest
  fetching a 404 and their posts silently never appear. Cleanup is a separate
  pass over anything older than a day.

* **Only a total failure raises.** With one network that is the old behaviour
  exactly; with five, raising after a partial success would throw away the
  posts that did land.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

from social.models import SocialSettings, TikTokDailyPick, VideoDelivery
from social.services import tiktok_budget, video_networks
from social.services.media_urls import site_base
from social.services.tiktok_montage import (
    COUNT_START,
    build_montage,
    ffmpeg_available,
)
from social.services.tiktok_music import absolute_track_path, pick_track
from social.services.tiktok_rotation import mark_failed, mark_partial, mark_published
from social.services.tiktok_script import build_script
from social.services.tiktok_video import generate_video_for_pick

logger = logging.getLogger(__name__)

MONTAGE_DIR = "social/tiktok/final"

# How long a published montage stays on disk. Long enough that every network
# has finished fetching it, short enough that the droplet does not fill up.
MEDIA_RETENTION_HOURS = 24

# Cover frame: after the question has faded in, before the first countdown
# digit lands. Frame zero would be the bare still, which reads as an empty
# thumbnail in the feed.
COVER_TIMESTAMP_MS = int((COUNT_START - 0.1) * 1000)


class TikTokPipelineError(RuntimeError):
    pass


def _notify(text: str) -> None:
    """
    Report to the video-networks topic; a notification failure never aborts a run.

    Routed away from the product-comment stream on purpose: these are daily
    operational reports, and mixing them into the topic used for answering
    customers buries the comments that actually need a reply.
    """
    try:
        from social.services.comment_notify import notify_staff_text

        notify_staff_text(text, video=True)
    except Exception:
        logger.exception("video report could not be delivered")


def _delete(path: str) -> None:
    if not path:
        return
    try:
        if default_storage.exists(path):
            default_storage.delete(path)
    except Exception:
        logger.exception("could not delete %s", path)


def build_final_video(pick: TikTokDailyPick, *, regenerate: bool = False) -> str:
    """
    Produce the montage for a pick and return its storage path.

    The raw clip is reused whenever the pick already has one: a publish that
    failed on a network's side must not pay for a second video. Only
    `regenerate` buys a new clip — retrying a failed post does not.

    The montage is reused on the same terms. This matters more than it looks:
    the staggered rollout calls publish_pick every ten minutes, and an
    unconditional render would put ffmpeg on a two-core droplet 144 times a
    day, competing with the site for CPU the whole evening.
    """
    if not ffmpeg_available():
        raise TikTokPipelineError("ffmpeg is not installed in this environment")

    relative = f"{MONTAGE_DIR}/pick-{pick.pk}.mp4"
    if not regenerate and (Path(settings.MEDIA_ROOT) / relative).exists():
        if pick.montage_path != relative:
            pick.montage_path = relative
            pick.save(update_fields=["montage_path", "updated"])
        return relative

    if not pick.video_path or regenerate:
        generate_video_for_pick(pick, force=regenerate)
        pick.refresh_from_db()

    clip = Path(settings.MEDIA_ROOT) / pick.video_path
    if not clip.exists():
        raise TikTokPipelineError(f"generated clip is missing: {clip}")

    script = build_script(pick)
    track = pick_track(pick.pk)
    target = Path(settings.MEDIA_ROOT) / relative
    build_montage(
        str(clip),
        script,
        str(target),
        music_path=absolute_track_path(track) if track else "",
    )
    if pick.montage_path != relative:
        pick.montage_path = relative
        pick.save(update_fields=["montage_path", "updated"])
    return relative


def _stagger_anchor(pick: TikTokDailyPick):
    """
    When this pick's rollout began — the moment every delay counts from.

    Taken from the first network that actually published rather than a stored
    timestamp: it survives a retry, a restart and a run that died halfway, all
    without another column.
    """
    first = (
        pick.deliveries.filter(published_at__isnull=False)
        .order_by("published_at")
        .first()
    )
    return first.published_at if first else timezone.now()


def _minutes_until_due(adapter, anchor) -> int:
    """Whole minutes left before this network's slot, 0 when it is time."""
    delay = int(getattr(adapter, "delay_minutes", 0) or 0)
    if delay <= 0:
        return 0
    due = anchor + timedelta(minutes=delay)
    remaining = (due - timezone.now()).total_seconds()
    return max(0, int(-(-remaining // 60)))


def _deliveries_for(pick: TikTokDailyPick) -> dict[str, VideoDelivery]:
    """One row per network, created on first use and reused on every retry."""
    rows = {}
    for adapter in video_networks.all_adapters():
        row, _ = VideoDelivery.objects.get_or_create(pick=pick, platform=adapter.key)
        rows[adapter.key] = row
    return rows


def publish_pick(
    pick: TikTokDailyPick, *, force: bool = False, regenerate: bool = False
) -> dict:
    """
    Send a pick's video to every enabled network.

    `force` bypasses the enabled toggles and the already-published guard;
    `regenerate` is separate and buys a new video. Keeping them apart matters:
    retrying a post a network rejected should cost nothing, and conflating the
    two once paid for four videos where one was needed.

    A network that already succeeded is never posted to twice, so a retry only
    picks up what is still outstanding.

    Raises only when nothing at all got published.
    """
    social = SocialSettings.load()

    # Cheapest and most consequential guard first: a retried cron must never
    # republish a pick that already went out everywhere.
    #
    # PARTIAL deliberately does NOT block. It means some network is still
    # outstanding, and that is precisely what a retry is for — the per-delivery
    # guard below is what stops the networks that already succeeded from being
    # posted to twice. (PARTIAL still retires the product from the rotation;
    # that is a separate question — see TikTokDailyPick.SPENT_STATUSES.)
    if pick.status == TikTokDailyPick.Status.PUBLISHED and not force:
        logger.info("video pick #%s already published", pick.pk)
        return {"already_published": True}
    if pick.product_id is None:
        raise TikTokPipelineError("Pick has no product")

    # Gate on operator intent only. A network that is switched on but missing
    # credentials is a SKIPPED delivery with a readable reason, not a reason to
    # refuse the whole run — the other networks may well be fine.
    if not any(a.is_enabled(social) for a in video_networks.all_adapters()) and not force:
        raise TikTokPipelineError("No video network is enabled in Social settings")

    targets = video_networks.plan_targets(social)

    # Build once, before touching any network: a montage failure is not a
    # per-network problem and must not leave half the deliveries marked failed.
    try:
        script = build_script(pick)
        montage_path = build_final_video(pick, regenerate=regenerate)
        video_url = f"{site_base()}{settings.MEDIA_URL}{montage_path}"
        if not video_url.startswith("https://"):
            raise TikTokPipelineError(
                f"video_url must be public HTTPS for PULL_FROM_URL: {video_url}"
            )
        local_path = str(Path(settings.MEDIA_ROOT) / montage_path)
    except Exception as exc:
        mark_failed(pick, str(exc))
        _notify(
            f"❌ Відео: не вдалося зібрати\n"
            f"Товар: {pick.product}\n"
            f"Помилка: {str(exc)[:400]}\n"
            f"Файли залишено для розбору."
        )
        raise

    rows = _deliveries_for(pick)
    published: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    waiting: list[str] = []
    results: dict[str, dict] = {}
    anchor = _stagger_anchor(pick)

    for adapter, initial in targets:
        row = rows[adapter.key]

        if initial == VideoDelivery.Status.SKIPPED and not force:
            reason = video_networks.skip_reason(adapter, social)
            row.mark(VideoDelivery.Status.SKIPPED, error=reason)
            skipped.append(f"{adapter.label} — {reason}")
            continue

        # Idempotency: never post twice to a network that already took it.
        if row.is_success and not force:
            published.append(f"{adapter.label} — вже було")
            continue

        due_in = _minutes_until_due(adapter, anchor)
        if due_in > 0 and not force:
            waiting.append(f"{adapter.label} — через {due_in} хв")
            continue

        try:
            caption = adapter.caption(pick, script)
            row.mark(VideoDelivery.Status.PUBLISHING)
            logger.info("video publish pick=%s network=%s", pick.pk, adapter.key)
            result = adapter.publish(
                pick=pick,
                script=script,
                caption=caption,
                video_url=video_url,
                local_path=local_path,
            )
        except Exception as exc:
            logger.exception("video publish failed pick=%s network=%s", pick.pk, adapter.key)
            row.mark(VideoDelivery.Status.FAILED, error=str(exc))
            failed.append(f"{adapter.label} — {str(exc)[:200]}")
            continue

        status = (
            VideoDelivery.Status.PUBLISHED_PRIVATE
            if result.get("private")
            else VideoDelivery.Status.PUBLISHED
        )
        row.mark(
            status,
            external_id=str(result.get("external_id") or ""),
            post_id=str(result.get("post_id") or ""),
            external_url=str(result.get("external_url") or ""),
        )
        results[adapter.key] = dict(result)
        published.append(
            f"{adapter.label} — {'приватно' if result.get('private') else 'опубліковано'}"
        )

    # A pick still waiting on a slot is not finished, and calling it PUBLISHED
    # now would stop the retry that has to deliver the rest.
    outcome = (
        TikTokDailyPick.Status.GENERATED
        if waiting and published
        else _record_outcome(pick, published=published, failed=failed)
    )

    if not published and not waiting:
        error = "; ".join(failed) or "жодна площадка не увімкнена"
        _notify(
            f"❌ Відео: пост не вийшов\n"
            f"Товар: {pick.product}\n"
            f"Помилка: {error[:400]}\n"
            f"Файли залишено для розбору."
        )
        raise TikTokPipelineError(error)

    # Only report once the rollout is over. A message per network would
    # turn the topic into a ticker nobody reads.
    if not waiting:
        _notify(_summary_text(pick, script, published, failed, skipped))
    return {
        "status": outcome,
        "published": published,
        "failed": failed,
        "skipped": skipped,
        "waiting": waiting,
        "results": results,
    }


def _record_outcome(pick: TikTokDailyPick, *, published: list[str], failed: list[str]) -> str:
    """PUBLISHED when nothing failed, PARTIAL when something did."""
    if not published:
        mark_failed(pick, "; ".join(failed) or "no network published")
        return TikTokDailyPick.Status.FAILED
    if failed:
        mark_partial(pick, "; ".join(failed))
        return TikTokDailyPick.Status.PARTIAL
    mark_published(pick)
    return TikTokDailyPick.Status.PUBLISHED


def _summary_text(
    pick: TikTokDailyPick,
    script: dict,
    published: list[str],
    failed: list[str],
    skipped: list[str],
) -> str:
    head = "✅ Відео: опубліковано" if not failed else "⚠️ Відео: опубліковано частково"
    lines = [
        head,
        f"Товар: {pick.product}",
        f"{script['price']} · {script['size']}",
        "",
    ]
    lines += [f"• {item}" for item in published]
    lines += [f"✖ {item}" for item in failed]
    lines += [f"– {item}" for item in skipped]

    status = tiktok_budget.budget_status()
    lines += ["", f"Витрачено за місяць: ${status['spent_usd']} з ${status['ceiling_usd']}"]
    return "\n".join(lines)


def cleanup_old_media(*, max_age_hours: int = MEDIA_RETENTION_HOURS, now=None) -> int:
    """
    Delete montages and clips whose networks have long since fetched them.

    Age-based rather than fired on publish: several networks pull the file
    asynchronously, and YouTube reads it off disk, so "the first network
    confirmed" is not a safe moment to delete anything.

    Picks still waiting to publish are left alone regardless of age — the file
    is the only thing standing between a retry and paying for a new video.
    """
    now = now or timezone.now()
    cutoff = now - timedelta(hours=max_age_hours)
    removed = 0

    stale = TikTokDailyPick.objects.filter(
        picked_at__lt=cutoff,
        status__in=(
            TikTokDailyPick.Status.PUBLISHED,
            TikTokDailyPick.Status.PARTIAL,
        ),
    ).exclude(video_path="", montage_path="")

    for pick in stale:
        for field in ("montage_path", "video_path"):
            path = getattr(pick, field)
            if not path:
                continue
            _delete(path)
            setattr(pick, field, "")
            removed += 1
        pick.save(update_fields=["montage_path", "video_path", "updated"])

    if removed:
        logger.info("video cleanup: removed %s files older than %sh", removed, max_age_hours)
    return removed
