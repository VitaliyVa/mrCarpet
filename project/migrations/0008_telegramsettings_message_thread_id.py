# Generated manually for TelegramSettings.message_thread_id

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("project", "0007_telegram_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramsettings",
            name="message_thread_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Для груп з топіками (Topics). "
                    "Напиши /start боту всередині потрібного топіку → getUpdates → message_thread_id. "
                    "Порожньо = General (часто закритий → TOPIC_CLOSED)."
                ),
                max_length=32,
                verbose_name="Topic ID (forum)",
            ),
        ),
    ]
