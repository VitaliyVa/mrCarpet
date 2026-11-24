"""Release SocialPosts whose scheduled_at has come.

Called by the content_scheduler daemon every 5 minutes (compose service
content-scheduler, always on). The tiktok_scheduler tick calls it too, but
that service is paused in prod; the claim guard below makes running both
harmless. Publishing runs synchronously here: the scheduler is already a background
process, and a daemon thread would only add a second place to lose errors.

Exactly once: a post is claimed by a conditional UPDATE (SCHEDULED →
PUBLISHING, guarded by the old status). Two overlapping ticks, or a tick and
an admin click, race on that single row update and only one of them gets
rowcount 1. A post that crashes mid-publish stays PUBLISHING and is never
retried automatically: a duplicate carousel on Instagram is worse than a
missed one, and the admin shows the state.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from social.models import SocialPost

logger = logging.getLogger(__name__)

#: A tick that finds a backlog (scheduler was down for a day) still releases
#: them gradually instead of firing a dozen posts within a minute.
MAX_PER_TICK = 3


def due_posts(now=None):
    now = now or timezone.now()
    return (
        SocialPost.objects.filter(
            status=SocialPost.Status.SCHEDULED,
            scheduled_at__isnull=False,
            scheduled_at__lte=now,
        )
        .select_related("article")
        .order_by("scheduled_at", "pk")
    )


def _claim(post_id: int, now) -> bool:
    """Atomically move one post SCHEDULED → PUBLISHING. True if we won it."""
    return bool(
        SocialPost.objects.filter(
            pk=post_id,
            status=SocialPost.Status.SCHEDULED,
            scheduled_at__lte=now,
        ).update(status=SocialPost.Status.PUBLISHING, updated=timezone.now())
    )


def release_due_posts(now=None, *, limit: int = MAX_PER_TICK) -> list[str]:
    """
    Publish every due scheduled post, at most `limit` per call.

    Returns short human lines for the scheduler log. A post whose linked
    article is not public yet (still a draft, or scheduled later than the
    post) is skipped and stays SCHEDULED: it goes out on the first tick after
    the article does, never before, so the link in the caption never 404s.
    """
    from social.services.publish import publish_post

    now = now or timezone.now()
    lines: list[str] = []
    released = 0
    for post in due_posts(now):
        if released >= limit:
            break
        if post.article_id and not post.article.is_public_at(now):
            lines.append(f"post #{post.pk}: waits for article «{post.article.slug}»")
            continue
        if not _claim(post.pk, now):
            continue
        released += 1
        try:
            result = publish_post(post.pk)
            lines.append(f"post #{post.pk}: {result.status}")
        except Exception as exc:
            logger.exception("scheduled publish failed post_id=%s", post.pk)
            SocialPost.objects.filter(pk=post.pk).update(
                status=SocialPost.Status.FAILED,
                last_error=f"scheduled publish crashed: {exc}"[:2000],
                updated=timezone.now(),
            )
            lines.append(f"post #{post.pk}: failed ({exc})")
    return lines


def schedule_post(post: SocialPost, at) -> None:
    post.scheduled_at = at
    post.status = SocialPost.Status.SCHEDULED
    post.last_error = ""
    post.save(update_fields=["scheduled_at", "status", "last_error", "updated"])


def unschedule_post(post: SocialPost) -> bool:
    """Back to draft, only if it has not started publishing."""
    return bool(
        SocialPost.objects.filter(
            pk=post.pk, status=SocialPost.Status.SCHEDULED
        ).update(status=SocialPost.Status.DRAFT, updated=timezone.now())
    )
