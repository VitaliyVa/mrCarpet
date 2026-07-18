# Generated manually for TelegramSettings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("project", "0006_stock_inquiry"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramSettings",
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
                    "bot_token",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Від @BotFather. Формат: 123456:ABC-DEF...",
                        max_length=255,
                        verbose_name="Bot token",
                    ),
                ),
                (
                    "chat_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="ID групи/супергрупи (зазвичай від’ємний, напр. -100123…) або особистого чату.",
                        max_length=64,
                        verbose_name="Chat ID",
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Якщо вимкнено — повідомлення не надсилаються.",
                        verbose_name="Увімкнено",
                    ),
                ),
                (
                    "notify_orders",
                    models.BooleanField(default=True, verbose_name="Замовлення"),
                ),
                (
                    "notify_contacts",
                    models.BooleanField(
                        default=True, verbose_name="Контактні форми"
                    ),
                ),
                (
                    "notify_stock",
                    models.BooleanField(
                        default=True, verbose_name="Запити наявності"
                    ),
                ),
            ],
            options={
                "verbose_name": "Налаштування Telegram",
                "verbose_name_plural": "Налаштування Telegram",
            },
        ),
    ]
