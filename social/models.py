"""Social publishing models."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from s_content.models import AbstractCreatedUpdated


class SocialSettings(models.Model):
    """Singleton runtime toggles (tokens live in env)."""

    tiktok_audit_passed = models.BooleanField(
        default=False,
        help_text="Увімкни після успішного TikTok Content Posting API audit.",
    )
    ai_i2v_enabled = models.BooleanField(
        default=True,
        help_text="Дозволити генерацію draft-відео через Replicate Wan I2V.",
    )
    ai_i2v_daily_limit = models.PositiveSmallIntegerField(
        default=10,
        help_text="Макс. AI генерацій на календарний день.",
    )
    ai_i2v_model = models.CharField(
        max_length=128,
        default="wan-video/wan-2.2-i2v-fast",
        blank=True,
    )
    auto_post_new_products_tg = models.BooleanField(
        default=False,
        help_text="Автоматично слати нові товари в TG products channel.",
    )
    auto_post_new_products_meta = models.BooleanField(
        default=False,
        help_text=(
            "Автоматично публікувати нові товари в Instagram/Facebook "
            "(photos-пост з головного фото + галереї)."
        ),
    )
    viber_posting_enabled = models.BooleanField(
        default=False,
        help_text=(
            "Майстер-рубильник Viber-каналу. Вимкнено = у Viber не постить "
            "НІЩО (ні авто, ні ручна дія в адмінці)."
        ),
    )
    auto_post_new_products_viber = models.BooleanField(
        default=False,
        help_text=(
            "Автоматично слати нові товари у Viber-канал "
            "(діє лише разом з увімкненим майстер-рубильником)."
        ),
    )
    products_channel_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Telegram channel id (напр. -100…).",
    )
    products_discussion_chat_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Linked discussion group id для коментарів.",
    )
    products_bot_replies = models.BooleanField(
        default=False,
        help_text=(
            "Застарілий FAQ-автоответчик у discussion (краще вимкнено). "
            "Коментарі дублюються в staff comments chat незалежно від цього."
        ),
    )
    staff_comments_enabled = models.BooleanField(
        default=True,
        help_text="Дублювати коментарі (TG discussion; пізніше IG/FB) у staff topic/чат.",
    )
    staff_comments_chat_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "Куди слати алерти. Порожньо = сімейна група (TelegramSettings.chat_id). "
            "Для forum-топіка зазвичай лишай порожнім."
        ),
    )
    staff_comments_thread_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "Forum topic id у сімейній групі (напр. «mr.Carpet comments»). "
            "Обов’язково ≠ orders message_thread_id."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Social settings"
        verbose_name_plural = "Social settings"

    def __str__(self) -> str:
        return "Social settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SocialSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SocialPost(AbstractCreatedUpdated):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        PUBLISHING = "publishing", "Publishing"
        PUBLISHED = "published", "Published"
        PARTIAL = "partial", "Partial success"
        FAILED = "failed", "Failed"

    class MediaKind(models.TextChoices):
        VIDEO = "video", "Video"
        PHOTOS = "photos", "Photo gallery"

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="social_posts",
    )
    media_kind = models.CharField(
        max_length=16,
        choices=MediaKind.choices,
        default=MediaKind.VIDEO,
        db_index=True,
        help_text="video → Reels/FB/TT video; photos → IG/FB/TT photo carousel.",
    )
    video = models.FileField(
        upload_to="social/videos/%Y/%m/",
        blank=True,
        help_text="MP4, бажано 9:16, 5–90 с для Reels.",
    )
    cover = models.ImageField(
        upload_to="social/covers/%Y/%m/",
        blank=True,
    )
    caption = models.TextField(
        blank=True,
        help_text="Базовий підпис (fallback для всіх платформ).",
    )
    caption_ig = models.TextField(blank=True)
    caption_fb = models.TextField(blank=True)
    caption_tt = models.TextField(blank=True)
    promo_code = models.CharField(max_length=64, blank=True, default="")
    utm_campaign = models.CharField(max_length=64, blank=True, default="social")

    target_instagram = models.BooleanField(default=True)
    target_facebook = models.BooleanField(default=True)
    target_tiktok = models.BooleanField(default=False)

    # TikTok compliance (audit-ready UI)
    tt_privacy_level = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Обери явно: PUBLIC_TO_EVERYONE / MUTUAL_FOLLOW_FRIENDS / SELF_ONLY. Без default.",
    )
    tt_allow_comment = models.BooleanField(default=True)
    tt_allow_duet = models.BooleanField(default=False)
    tt_allow_stitch = models.BooleanField(default=False)
    tt_commercial_disclosure = models.BooleanField(
        default=False,
        help_text="Your brand / branded content disclosure (TikTok).",
    )
    tt_music_usage_confirmed = models.BooleanField(
        default=False,
        help_text="Підтвердження music usage перед публікацією в TikTok.",
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    ai_generated = models.BooleanField(default=False)
    ai_prompt = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created",)
        verbose_name = "Social post"
        verbose_name_plural = "Social posts"

    def __str__(self) -> str:
        label = self.product.title if self.product_id else f"#{self.pk}"
        return f"SocialPost {self.pk}: {label} [{self.status}]"

    def caption_for(self, platform: str) -> str:
        mapping = {
            "instagram": self.caption_ig,
            "facebook": self.caption_fb,
            "tiktok": self.caption_tt,
        }
        specific = (mapping.get(platform) or "").strip()
        return specific or (self.caption or "").strip()

    def product_url(self) -> str:
        from social.services.media_urls import product_share_url

        return product_share_url(self)

    def ordered_images(self):
        return self.images.order_by("sort_order", "id")


class SocialPostImage(AbstractCreatedUpdated):
    post = models.ForeignKey(
        SocialPost,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="social/images/%Y/%m/")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Social post image"
        verbose_name_plural = "Social post images"

    def __str__(self) -> str:
        return f"SocialPostImage {self.pk} post={self.post_id} #{self.sort_order}"


class SocialDelivery(AbstractCreatedUpdated):
    class Platform(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        TIKTOK = "tiktok", "TikTok"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        UPLOADING = "uploading", "Uploading"
        PUBLISHED = "published", "Published"
        PUBLISHED_PRIVATE = "published_private", "Published (private/self-only)"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    post = models.ForeignKey(
        SocialPost,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    platform = models.CharField(max_length=16, choices=Platform.choices)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    external_id = models.CharField(max_length=128, blank=True, default="")
    external_url = models.URLField(blank=True, default="")
    error = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created",)
        unique_together = (("post", "platform"),)
        verbose_name = "Social delivery"
        verbose_name_plural = "Social deliveries"

    def __str__(self) -> str:
        return f"{self.platform} [{self.status}] post={self.post_id}"

    def mark(self, status: str, *, error: str = "", external_id: str = "", external_url: str = ""):
        self.status = status
        self.attempts = (self.attempts or 0) + 1
        if error:
            self.error = error[:4000]
        if external_id:
            self.external_id = external_id
        if external_url:
            self.external_url = external_url
        if status in (
            self.Status.PUBLISHED,
            self.Status.PUBLISHED_PRIVATE,
            self.Status.FAILED,
            self.Status.SKIPPED,
        ):
            self.finished_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "attempts",
                "error",
                "external_id",
                "external_url",
                "finished_at",
                "updated",
            ]
        )


class SocialAiGenerationLog(models.Model):
    """Daily budget tracking for Wan I2V."""

    day = models.DateField(db_index=True)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (("day",),)

    @classmethod
    def increment_today(cls) -> int:
        today = timezone.localdate()
        obj, _ = cls.objects.get_or_create(day=today, defaults={"count": 0})
        obj.count = (obj.count or 0) + 1
        obj.save(update_fields=["count"])
        return obj.count

    @classmethod
    def today_count(cls) -> int:
        today = timezone.localdate()
        obj = cls.objects.filter(day=today).first()
        return int(obj.count) if obj else 0
