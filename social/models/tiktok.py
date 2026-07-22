"""TikTok daily-pipeline models: source images, spend ledger, daily picks."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from s_content.models import AbstractCreatedUpdated


class TikTokVerticalImage(AbstractCreatedUpdated):
    """
    9:16 version of a product's interior photo, generated once and reused.

    p-video takes its output aspect ratio from the input image and ignores the
    aspect_ratio argument, so a vertical source is the only way to get vertical
    video. Our interior shots are 4:3, so the room is extended with the same
    image model the product pages already use.
    """

    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="tiktok_vertical_image",
    )
    source_image = models.ForeignKey(
        "catalog.ProductImage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Вихідне is_ai фото, з якого зроблено вертикаль.",
    )
    image = models.ImageField(upload_to="social/tiktok/vertical")
    model_name = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        verbose_name = "TikTok vertical image"
        verbose_name_plural = "TikTok vertical images"

    def __str__(self) -> str:
        return f"9:16 for {self.product.title[:50]}"


class TikTokGenerationSpend(AbstractCreatedUpdated):
    """
    Ledger of every paid generation call, successful or not.

    Failed attempts still cost money, so the monthly guard counts them too —
    otherwise a few retries could quietly blow through the ceiling.
    """

    class Kind(models.TextChoices):
        IMAGE = "image", "Вертикальне фото 9:16"
        VIDEO = "video", "Відео"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    model_name = models.CharField(max_length=128, blank=True, default="")
    cost_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    succeeded = models.BooleanField(default=False)
    pick = models.ForeignKey(
        "social.TikTokDailyPick",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spends",
    )
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("-created",)
        verbose_name = "TikTok generation spend"
        verbose_name_plural = "TikTok generation spend"
        indexes = [models.Index(fields=["-created"])]

    def __str__(self) -> str:
        state = "ok" if self.succeeded else "FAILED"
        return f"{self.kind} ${self.cost_usd} [{state}]"


class TikTokDailyPick(AbstractCreatedUpdated):
    """
    One product per day for the TikTok auto-poster, without repeats.

    Only PUBLISHED picks retire a product from the current cycle: a video that
    was generated but never made it to TikTok would otherwise silently drop the
    product until the whole catalogue has been through, and a failure would
    punish the product rather than the run. When every eligible product has
    been published the cycle number advances and the pool starts over.
    """

    class Status(models.TextChoices):
        GENERATED = "generated", "Відео згенеровано"
        PUBLISHED = "published", "Опубліковано"
        PARTIAL = "partial", "Опубліковано частково"
        FAILED = "failed", "Помилка"

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tiktok_picks",
        help_text="Порожньо = товар видалили після піку (історія лишається).",
    )
    cycle_number = models.PositiveIntegerField(default=1)
    picked_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.GENERATED,
    )
    social_post = models.ForeignKey(
        "social.SocialPost",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tiktok_picks",
    )
    video_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Сирий кліп з моделі; чиститься проходом по віку.",
    )
    montage_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Готовий монтаж, який тягнуть площадки; чиститься проходом по віку.",
    )
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-picked_at", "-id")
        verbose_name = "TikTok daily pick"
        verbose_name_plural = "TikTok daily picks"
        indexes = [
            models.Index(fields=["cycle_number", "status"]),
            models.Index(fields=["-picked_at"]),
        ]

    def __str__(self) -> str:
        title = self.product.title if self.product_id else "(видалений товар)"
        return f"TikTokDailyPick #{self.pk}: {title} [{self.status}] cycle={self.cycle_number}"

    #: Statuses that retire the product for this cycle.
    #
    #: PARTIAL counts. A pick that reached TikTok but failed on Threads has
    #: still been seen by an audience, so returning the product to the pool
    #: would republish it where it already ran. Success is "at least one
    #: network", deliberately not "every network" — do not "fix" this to all().
    SPENT_STATUSES = ("published", "partial")

    @property
    def is_spent(self) -> bool:
        return self.status in self.SPENT_STATUSES
