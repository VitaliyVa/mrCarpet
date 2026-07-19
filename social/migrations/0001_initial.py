# Generated manually for social app initial schema

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0045_promocode_end_time_optional"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialAiGenerationLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("day", models.DateField(db_index=True)),
                ("count", models.PositiveIntegerField(default=0)),
            ],
            options={
                "unique_together": {("day",)},
            },
        ),
        migrations.CreateModel(
            name="SocialSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "tiktok_audit_passed",
                    models.BooleanField(
                        default=False,
                        help_text="Увімкни після успішного TikTok Content Posting API audit.",
                    ),
                ),
                (
                    "ai_i2v_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Дозволити генерацію draft-відео через Replicate Wan I2V.",
                    ),
                ),
                (
                    "ai_i2v_daily_limit",
                    models.PositiveSmallIntegerField(
                        default=10,
                        help_text="Макс. AI генерацій на календарний день.",
                    ),
                ),
                (
                    "ai_i2v_model",
                    models.CharField(
                        blank=True,
                        default="wan-video/wan-2.2-i2v-fast",
                        max_length=128,
                    ),
                ),
                (
                    "auto_post_new_products_tg",
                    models.BooleanField(
                        default=False,
                        help_text="Автоматично слати нові товари в TG products channel.",
                    ),
                ),
                (
                    "products_channel_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Telegram channel id (напр. -100…).",
                        max_length=64,
                    ),
                ),
                (
                    "products_discussion_chat_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Linked discussion group id для коментарів.",
                        max_length=64,
                    ),
                ),
                (
                    "products_bot_replies",
                    models.BooleanField(
                        default=True,
                        help_text="Бот відповідає на whitelist-питання в discussion group.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Social settings",
                "verbose_name_plural": "Social settings",
            },
        ),
        migrations.CreateModel(
            name="SocialPost",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, blank=True, null=True, verbose_name="Created"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, blank=True, null=True, verbose_name="Updated"
                    ),
                ),
                (
                    "video",
                    models.FileField(
                        blank=True,
                        help_text="MP4, бажано 9:16, 5–90 с для Reels.",
                        upload_to="social/videos/%Y/%m/",
                    ),
                ),
                (
                    "cover",
                    models.ImageField(blank=True, upload_to="social/covers/%Y/%m/"),
                ),
                (
                    "caption",
                    models.TextField(
                        blank=True,
                        help_text="Базовий підпис (fallback для всіх платформ).",
                    ),
                ),
                ("caption_ig", models.TextField(blank=True)),
                ("caption_fb", models.TextField(blank=True)),
                ("caption_tt", models.TextField(blank=True)),
                ("promo_code", models.CharField(blank=True, default="", max_length=64)),
                (
                    "utm_campaign",
                    models.CharField(blank=True, default="social", max_length=64),
                ),
                ("target_instagram", models.BooleanField(default=True)),
                ("target_facebook", models.BooleanField(default=True)),
                ("target_tiktok", models.BooleanField(default=False)),
                (
                    "tt_privacy_level",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Обери явно: PUBLIC_TO_EVERYONE / MUTUAL_FOLLOW_FRIENDS / SELF_ONLY. Без default.",
                        max_length=32,
                    ),
                ),
                ("tt_allow_comment", models.BooleanField(default=True)),
                ("tt_allow_duet", models.BooleanField(default=False)),
                ("tt_allow_stitch", models.BooleanField(default=False)),
                (
                    "tt_commercial_disclosure",
                    models.BooleanField(
                        default=False,
                        help_text="Your brand / branded content disclosure (TikTok).",
                    ),
                ),
                (
                    "tt_music_usage_confirmed",
                    models.BooleanField(
                        default=False,
                        help_text="Підтвердження music usage перед публікацією в TikTok.",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("queued", "Queued"),
                            ("publishing", "Publishing"),
                            ("published", "Published"),
                            ("partial", "Partial success"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("ai_generated", models.BooleanField(default=False)),
                ("ai_prompt", models.TextField(blank=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="social_posts",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Social post",
                "verbose_name_plural": "Social posts",
                "ordering": ("-created",),
            },
        ),
        migrations.CreateModel(
            name="SocialDelivery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, blank=True, null=True, verbose_name="Created"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, blank=True, null=True, verbose_name="Updated"
                    ),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("instagram", "Instagram"),
                            ("facebook", "Facebook"),
                            ("tiktok", "TikTok"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("uploading", "Uploading"),
                            ("published", "Published"),
                            ("published_private", "Published (private/self-only)"),
                            ("failed", "Failed"),
                            ("skipped", "Skipped"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=32,
                    ),
                ),
                (
                    "external_id",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("external_url", models.URLField(blank=True, default="")),
                ("error", models.TextField(blank=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "post",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="social.socialpost",
                    ),
                ),
            ],
            options={
                "verbose_name": "Social delivery",
                "verbose_name_plural": "Social deliveries",
                "ordering": ("-created",),
                "unique_together": {("post", "platform")},
            },
        ),
    ]
