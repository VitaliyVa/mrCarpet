from django.db import migrations, models


def set_initial_sort_order(apps, schema_editor):
    ProductImage = apps.get_model("catalog", "ProductImage")
    by_product = {}
    for img in ProductImage.objects.all().order_by("id"):
        by_product.setdefault(img.product_id, []).append(img)
    for images in by_product.values():
        for index, img in enumerate(images):
            img.sort_order = (index + 1) * 10
            img.save(update_fields=["sort_order"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0037_colorgroup_product_color_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="productimage",
            name="sort_order",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Менше число — вище в слайдері на сторінці товару",
                verbose_name="Порядок",
            ),
        ),
        migrations.AlterModelOptions(
            name="productimage",
            options={
                "ordering": ["sort_order", "id"],
                "verbose_name": "Зображення продукта",
                "verbose_name_plural": "Зображення продуктів",
            },
        ),
        migrations.RunPython(set_initial_sort_order, migrations.RunPython.noop),
    ]
