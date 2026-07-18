# Generated manually for Telegram AI agent

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("project", "0008_telegramsettings_message_thread_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramsettings",
            name="ai_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Двосторонній агент (wake words / згадка / reply). Потрібен REPLICATE_API_TOKEN.",
                verbose_name="AI агент увімкнено",
            ),
        ),
        migrations.AddField(
            model_name="telegramsettings",
            name="ai_rate_limit_per_user",
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text="Макс. AI-запитів на одного Telegram user за 10 хвилин.",
                verbose_name="AI rate limit / 10 хв",
            ),
        ),
        migrations.AddField(
            model_name="telegramsettings",
            name="replicate_model",
            field=models.CharField(
                blank=True,
                default="meta/meta-llama-3-8b-instruct",
                help_text="Slug моделі на Replicate, напр. meta/meta-llama-3-8b-instruct",
                max_length=255,
                verbose_name="Replicate model",
            ),
        ),
        migrations.AddField(
            model_name="telegramsettings",
            name="wake_words",
            field=models.TextField(
                blank=True,
                default=(
                    "містер карпет\nмистер карпет\nмр карпет\nмістеркарпет\n"
                    "mr carpet\nmrcarpet\nmr.carpet\nmr carpet bot"
                ),
                help_text="По одному на рядок. Для wake words у BotFather вимкни Group Privacy.",
                verbose_name="Wake words",
            ),
        ),
        migrations.AddField(
            model_name="telegramsettings",
            name="webhook_secret",
            field=models.CharField(
                blank=True,
                default="",
                help_text="X-Telegram-Bot-Api-Secret-Token для prod webhook.",
                max_length=128,
                verbose_name="Webhook secret",
            ),
        ),
        migrations.CreateModel(
            name="TelegramProcessedUpdate",
            fields=[
                (
                    "update_id",
                    models.BigIntegerField(primary_key=True, serialize=False, unique=True),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Telegram processed update",
                "verbose_name_plural": "Telegram processed updates",
            },
        ),
        migrations.CreateModel(
            name="TelegramChatMemory",
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
                ("chat_id", models.CharField(db_index=True, max_length=64)),
                (
                    "thread_id",
                    models.CharField(blank=True, db_index=True, default="", max_length=32),
                ),
                ("summary", models.TextField(blank=True, default="")),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Telegram chat memory",
                "verbose_name_plural": "Telegram chat memories",
                "unique_together": {("chat_id", "thread_id")},
            },
        ),
        migrations.CreateModel(
            name="TelegramChatMessage",
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
                ("chat_id", models.CharField(db_index=True, max_length=64)),
                (
                    "thread_id",
                    models.CharField(blank=True, db_index=True, default="", max_length=32),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("user", "User"),
                            ("assistant", "Assistant"),
                            ("tool", "Tool"),
                        ],
                        max_length=16,
                    ),
                ),
                ("content", models.TextField()),
                (
                    "tg_user_id",
                    models.BigIntegerField(blank=True, db_index=True, null=True),
                ),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "Telegram chat message",
                "verbose_name_plural": "Telegram chat messages",
                "ordering": ("created",),
            },
        ),
        migrations.CreateModel(
            name="TelegramPendingAction",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("tool_name", models.CharField(max_length=64)),
                ("args_json", models.JSONField(default=dict)),
                ("description", models.TextField(blank=True, default="")),
                ("created_by_tg_user", models.BigIntegerField(blank=True, null=True)),
                ("chat_id", models.CharField(max_length=64)),
                ("message_thread_id", models.CharField(blank=True, default="", max_length=32)),
                ("telegram_message_id", models.BigIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Очікує"),
                            ("confirmed", "Підтверджено"),
                            ("rejected", "Скасовано"),
                            ("expired", "Протерміновано"),
                            ("failed", "Помилка"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("result_text", models.TextField(blank=True, default="")),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Telegram pending action",
                "verbose_name_plural": "Telegram pending actions",
                "ordering": ("-created",),
            },
        ),
        migrations.AddIndex(
            model_name="telegramchatmessage",
            index=models.Index(
                fields=["chat_id", "thread_id", "-created"],
                name="project_tel_chat_id_7a2e1f_idx",
            ),
        ),
    ]
