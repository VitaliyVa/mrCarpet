from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("project", "0014_newsletter_campaigns"),
    ]

    operations = [
        migrations.AddField(
            model_name="newslettercampaign",
            name="hero_image",
            field=models.ImageField(
                blank=True,
                help_text=(
                    "Опційно завантаж своє фото. Якщо порожньо — при генерації "
                    "Replicate намалює hero (gpt-image-2 low) і оптимізує у WebP."
                ),
                null=True,
                upload_to="newsletter/heroes",
                verbose_name="Hero-фото листа",
            ),
        ),
        migrations.AddField(
            model_name="newslettercampaign",
            name="image_prompt",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Заповнюється текстовою моделлю під час генерації; "
                    "можна правити вручну."
                ),
                verbose_name="Промпт для фото (AI)",
            ),
        ),
    ]
