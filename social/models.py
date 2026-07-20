"""Social publishing models."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from s_content.models import AbstractCreatedUpdated


class SocialSettings(models.Model):
    """Singleton runtime toggles (tokens live in env)."""

    tiktok_audit_passed = models.BooleanField(
        default=False,
        help_text=(
            "⚠️ ЗНІМАЄ ЗАХИСТ. Поки вимкнено — усі пости йдуть SELF_ONLY "
            "(видно лише власнику). Увімкнення дозволяє ПУБЛІЧНІ пости й "
            "має сенс ЛИШЕ після реального схвалення TikTok audit. "
            "Це НЕ вмикач автопостингу — для нього є «Авто-генерація TikTok» нижче."
        ),
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
    tiktok_auto_enabled = models.BooleanField(
        default=False,
        help_text="Майстер-рубильник щоденної авто-генерації відео для TikTok.",
    )
    tiktok_video_model = models.CharField(
        max_length=128,
        default="prunaai/p-video",
        blank=True,
        help_text="Модель i2v. Пропорції беруться з вхідного фото, не з параметра.",
    )
    tiktok_video_seconds = models.PositiveSmallIntegerField(
        default=6,
        help_text="Тривалість відео. Ціна лінійна: $0.02/с на 720p.",
    )
    tiktok_video_resolution = models.CharField(
        max_length=8,
        default="720p",
        blank=True,
        help_text="720p ($0.02/с) або 1080p ($0.04/с — пробиває стелю $5/міс).",
    )
    tiktok_video_draft = models.BooleanField(
        default=False,
        help_text=(
            "Draft-режим: у 4 рази дешевше, але візерунок килима «пливе». "
            "Тільки для тестів, не для бойових постів."
        ),
    )
    tiktok_monthly_budget_usd = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=5,
        help_text=(
            "Жорстка стеля витрат на генерацію за календарний місяць. "
            "Рахуються ВСІ прогони, включно з невдалими."
        ),
    )
    tiktok_vertical_image_model = models.CharField(
        max_length=128,
        default="openai/gpt-image-2",
        blank=True,
        help_text="Модель, що перекадровує 4:3 фото в 9:16 (та сама, що для фото товарів).",
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
    video_comments_thread_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="Video topic (thread_id)",
        help_text=(
            "Окремий forum-топік для відео-мереж (TikTok/Reels/Threads/Shorts): "
            "звіти щоденного ролика і коментарі під ним. Порожньо = все падає "
            "у звичайний топік коментарів."
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


class TikTokToken(models.Model):
    """
    Singleton OAuth token store for the TikTok Content Posting API.

    TikTok has no never-expiring token: access_token lives 24h and
    refresh_token 365 days from the *initial* grant (not rolling). So the
    access token is refreshed in the background and the OAuth flow has to be
    repeated by a human roughly once a year — see refresh_expires_at.

    client_key is stored alongside the tokens because sandbox and production
    credentials are separate: a token minted for one client_key returns 401
    for the other, and that failure is otherwise indistinguishable from an
    expired token.
    """

    REFRESH_MARGIN_SECONDS = 600
    REAUTH_WARNING_DAYS = 30

    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    open_id = models.CharField(max_length=128, blank=True, default="")
    scope = models.CharField(max_length=255, blank=True, default="")
    client_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="client_key the tokens were issued for (sandbox keys start with 'sb').",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    refresh_expires_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    refresh_fail_count = models.PositiveIntegerField(default=0)
    reauth_warned_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "TikTok token"
        verbose_name_plural = "TikTok token"

    def __str__(self) -> str:
        if not self.access_token:
            return "TikTok token (not authorized)"
        return f"TikTok token open_id={self.open_id or '?'}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "TikTokToken":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_authorized(self) -> bool:
        return bool(self.access_token and self.refresh_token)

    @property
    def needs_refresh(self) -> bool:
        """True when the access token is missing or within the safety margin."""
        if not self.access_token or self.expires_at is None:
            return True
        margin = timezone.timedelta(seconds=self.REFRESH_MARGIN_SECONDS)
        return self.expires_at - timezone.now() <= margin

    @property
    def refresh_expired(self) -> bool:
        if self.refresh_expires_at is None:
            return False
        return timezone.now() >= self.refresh_expires_at

    @property
    def days_until_reauth(self) -> int | None:
        if self.refresh_expires_at is None:
            return None
        return (self.refresh_expires_at - timezone.now()).days


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
    ) -> "VideoDelivery":
        self.status = status
        self.error = (error or "")[:2000]
        if external_id:
            self.external_id = external_id[:190]
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
                "external_url",
                "attempts",
                "published_at",
                "updated",
            ]
        )
        return self


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


class SocialCommentReply(AbstractCreatedUpdated):
    """HITL-відповідь на комент із соцмережі через сімейний чат.

    Життєвий цикл: mirrored (алерт у staff topic) → awaiting_confirm
    (оператор reply-нув, LLM згенерував чернетку) → sent / cancelled / failed.
    """

    class Status(models.TextChoices):
        MIRRORED = "mirrored", "Mirrored to staff"
        AWAITING = "awaiting_confirm", "Awaiting confirm"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"

    platform = models.CharField(max_length=16, db_index=True)
    # IG/FB: id коментаря в Graph; TG: пусто (використовуються tg_* поля)
    external_comment_id = models.CharField(max_length=128, blank=True, default="")
    tg_chat_id = models.CharField(max_length=64, blank=True, default="")
    tg_message_id = models.CharField(max_length=64, blank=True, default="")

    comment_text = models.TextField(blank=True)
    author_name = models.CharField(max_length=256, blank=True, default="")
    post_url = models.URLField(blank=True, default="")

    # Де лежить копія в сімейній групі (ключ матчингу reply оператора)
    alert_chat_id = models.CharField(max_length=64, db_index=True)
    alert_message_id = models.CharField(max_length=64, db_index=True)

    raw_operator_text = models.TextField(blank=True)
    draft_text = models.TextField(blank=True)
    draft_message_id = models.CharField(max_length=64, blank=True, default="")
    drafted_by_tg_user = models.CharField(max_length=64, blank=True, default="")
    # Дедуп ретраїв Telegram: останнє оброблене повідомлення оператора
    last_operator_message_id = models.CharField(
        max_length=64, blank=True, default=""
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.MIRRORED,
        db_index=True,
    )
    sent_external_id = models.CharField(max_length=128, blank=True, default="")
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created",)
        verbose_name = "Social comment reply"
        verbose_name_plural = "Social comment replies"

    def __str__(self) -> str:
        return f"{self.platform} reply #{self.pk} [{self.status}]"


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
