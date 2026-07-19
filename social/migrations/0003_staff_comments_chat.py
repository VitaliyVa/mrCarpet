from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("social", "0002_media_kind_and_gallery"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialsettings",
            name="staff_comments_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Дублювати коментарі (TG discussion; пізніше IG/FB) у staff-чат.",
            ),
        ),
        migrations.AddField(
            model_name="socialsettings",
            name="staff_comments_chat_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Куди слати алерти. Порожньо = сімейна група (TelegramSettings.chat_id). "
                    "Для forum-топіка зазвичай лишай порожнім."
                ),
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="socialsettings",
            name="staff_comments_thread_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Forum topic id у сімейній групі (напр. «mr.Carpet comments»). "
                    "Обов’язково ≠ orders message_thread_id."
                ),
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="socialsettings",
            name="products_bot_replies",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Застарілий FAQ-автоответчик у discussion (краще вимкнено). "
                    "Коментарі дублюються в staff comments chat незалежно від цього."
                ),
            ),
        ),
    ]
