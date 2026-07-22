"""Daily-video delivery and per-day metric snapshots."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from s_content.models import AbstractCreatedUpdated


class VideoDelivery(AbstractCreatedUpdated):
    """
    One daily video, one row per network it was sent to.

    Kept apart from SocialDelivery on purpose: that model belongs to
    SocialPost — the *manual* posts composed in the admin — and hanging a
    daily pick off it would mean making post_id nullable, breaking the
    invariant that a delivery always belongs to a post. The two pipelines
    have different lifecycles and different sets of networks, so ~40 lines
    of duplication is cheaper than a premature shared abstraction.

    The unique constraint on (pick, platform) is what makes a retry safe:
    a run that published to TikTok and failed on Threads can be repeated
    without posting to TikTok twice.
    """

    class Platform(models.TextChoices):
        TIKTOK = "tiktok", "TikTok"
        INSTAGRAM = "instagram", "Instagram Reels"
        FACEBOOK = "facebook", "Facebook"
        THREADS = "threads", "Threads"
        YOUTUBE = "youtube", "YouTube Shorts"

    class Status(models.TextChoices):
        PENDING = "pending", "Очікує"
        PUBLISHING = "publishing", "Публікується"
        PUBLISHED = "published", "Опубліковано"
        # Posted, but only the owner can see it: TikTok before its audit and
        # YouTube before the compliance audit both force this.
        PUBLISHED_PRIVATE = "published_private", "Опубліковано приватно"
        FAILED = "failed", "Помилка"
        # Network switched off or not configured. Deliberately not FAILED:
        # otherwise the daily report cries about YouTube we never enabled.
        SKIPPED = "skipped", "Пропущено"

    TERMINAL_STATUSES = ("published", "published_private", "failed", "skipped")
    SUCCESS_STATUSES = ("published", "published_private")

    pick = models.ForeignKey(
        "social.TikTokDailyPick",
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    platform = models.CharField(max_length=16, choices=Platform.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    # Indexed because every inbound comment is matched against it to decide
    # which Telegram topic the alert belongs in.
    external_id = models.CharField(max_length=190, blank=True, default="", db_index=True)
    # Facebook hands back a video_id on publish but reports comments against a
    # post_id, and the two are different strings. Without this the daily Reel's
    # comments would never be recognised as belonging to a video.
    post_id = models.CharField(
        max_length=190,
        blank=True,
        default="",
        db_index=True,
        help_text="Ідентифікатор поста, коли він відрізняється від external_id (Facebook).",
    )
    external_url = models.URLField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("pick_id", "platform")
        verbose_name = "Video delivery"
        verbose_name_plural = "Video deliveries"
        unique_together = (("pick", "platform"),)
        indexes = [models.Index(fields=["status", "platform"])]

    def __str__(self) -> str:
        return f"{self.get_platform_display()} · pick #{self.pick_id} [{self.status}]"

    @property
    def is_success(self) -> bool:
        return self.status in self.SUCCESS_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    def mark(
        self,
        status: str,
        *,
        error: str = "",
        external_id: str = "",
        external_url: str = "",
        post_id: str = "",
    ) -> "VideoDelivery":
        self.status = status
        self.error = (error or "")[:2000]
        if external_id:
            self.external_id = external_id[:190]
        if post_id:
            self.post_id = post_id[:190]
        if external_url:
            self.external_url = external_url
        # Counted on the way in, not on the way out: a call that times out
        # after the network accepted the post must still show as an attempt.
        if status == self.Status.PUBLISHING:
            self.attempts += 1
        if status in self.SUCCESS_STATUSES and self.published_at is None:
            self.published_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "error",
                "external_id",
                "post_id",
                "external_url",
                "attempts",
                "published_at",
                "updated",
            ]
        )
        return self


class VideoMetric(AbstractCreatedUpdated):
    """
    One reading of a published video's counters, taken once a day.

    A snapshot rather than columns on VideoDelivery, because the question
    worth answering is not "how many views does this have" but "how many did
    it have after a day" — the only number comparable across networks that
    publish 80 minutes apart. Counters overwritten in place cannot answer it.

    Counts are nullable on purpose. Zero and "this network will not tell us"
    are different facts, and collapsing them would make Instagram look like it
    gets no views when it simply does not report them without a permission we
    have not asked for. Everything reading this model must keep them apart.

    Five rows a day is nothing for SQLite; no pruning is worth the code.
    """

    delivery = models.ForeignKey(
        "social.VideoDelivery",
        on_delete=models.CASCADE,
        related_name="metrics",
    )
    #: Local date the reading was taken. Together with delivery it makes the
    #: collector idempotent: running the scheduler twice updates one row.
    collected_on = models.DateField(db_index=True)
    views = models.PositiveIntegerField(null=True, blank=True)
    likes = models.PositiveIntegerField(null=True, blank=True)
    comments = models.PositiveIntegerField(null=True, blank=True)
    #: Hours between publishing and this reading, stored rather than derived:
    #: it makes "views after 24h" a query instead of arithmetic over two tables.
    age_hours = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-collected_on", "delivery_id")
        verbose_name = "Video metric"
        verbose_name_plural = "Video metrics"
        unique_together = (("delivery", "collected_on"),)

    def __str__(self) -> str:
        return f"{self.delivery_id} @ {self.collected_on}: {self.views} переглядів"
