from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0039_productimage_is_ai"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="ar_texture",
            field=models.ImageField(
                blank=True,
                help_text="PNG з alpha для 3D/AR. Генерується з каталожного фото або завантажується вручну.",
                null=True,
                upload_to="ar/textures",
                verbose_name="AR-текстура",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="ar_status",
            field=models.CharField(
                choices=[
                    ("none", "Немає"),
                    ("pending", "Генерується"),
                    ("ready", "Готово"),
                    ("failed", "Помилка"),
                ],
                db_index=True,
                default="none",
                max_length=16,
                verbose_name="Статус AR",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="ar_error",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Помилка AR",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="ar_updated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="AR оновлено",
            ),
        ),
    ]
