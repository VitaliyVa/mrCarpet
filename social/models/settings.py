"""Runtime settings singleton for the social pipeline."""

from __future__ import annotations

from django.db import models


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
    # Per-network switches for the daily video. TikTok keeps its historical
    # name (tiktok_auto_enabled) because it doubles as the master switch for
    # the generation step, which runs whether or not anything is published.
    video_instagram_enabled = models.BooleanField(
        default=False,
        verbose_name="Instagram Reels",
        help_text="Постити щоденний ролик у Reels. Потребує META_IG_USER_ID.",
    )
    video_facebook_enabled = models.BooleanField(
        default=False,
        verbose_name="Facebook",
        help_text="Постити щоденний ролик на сторінку. Потребує META_PAGE_ID.",
    )
    video_threads_enabled = models.BooleanField(
        default=False,
        verbose_name="Threads",
        help_text="Потребує окремого Threads-токена (не Meta page token).",
    )
    video_youtube_enabled = models.BooleanField(
        default=False,
        verbose_name="YouTube Shorts",
        help_text=(
            "Не вмикати до проходження YouTube compliance audit: без нього "
            "API мовчки робить відео приватним, і публічним його вже не "
            "зробити ніколи."
        ),
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
