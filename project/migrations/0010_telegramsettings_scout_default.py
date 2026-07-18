from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("project", "0009_telegram_ai_agent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="telegramsettings",
            name="replicate_model",
            field=models.CharField(
                blank=True,
                default="meta/llama-4-scout-instruct",
                help_text=(
                    "Slug на Replicate. Рекомендовано: meta/llama-4-scout-instruct "
                    "(розумніше за 8B, дешевше за 70B). Альтернативи: "
                    "meta/meta-llama-3-8b-instruct (дешевше), "
                    "meta/meta-llama-3-70b-instruct (дорожче/розумніше)."
                ),
                max_length=255,
                verbose_name="Replicate model",
            ),
        ),
    ]
