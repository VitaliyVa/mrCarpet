from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0038_productimage_sort_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="productimage",
            name="is_ai",
            field=models.BooleanField(
                default=False,
                help_text="Позначається автоматично для зображень, згенерованих у блоці «Генерація фото для сторінки товару»",
                verbose_name="Ілюстрація інтер'єру (ШІ)",
            ),
        ),
    ]
