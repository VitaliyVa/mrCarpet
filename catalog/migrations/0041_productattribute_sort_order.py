import re
from decimal import Decimal, InvalidOperation

from django.db import migrations, models

_FIRST_NUM = re.compile(r"([\d]+(?:[.,]\d+)?)")


def _first_number(label):
    if not label or not str(label).strip():
        return None
    match = _FIRST_NUM.search(str(label))
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None


def set_initial_sort_order(apps, schema_editor):
    ProductAttribute = apps.get_model("catalog", "ProductAttribute")
    Size = apps.get_model("catalog", "Size")
    size_titles = dict(Size.objects.values_list("id", "title"))

    by_product = {}
    for attr in ProductAttribute.objects.all().order_by("id"):
        by_product.setdefault(attr.product_id, []).append(attr)

    for attrs in by_product.values():

        def sort_key(attr):
            custom = 1 if attr.custom_attribute else 0
            label = size_titles.get(attr.size_id) or ""
            width = _first_number(label)
            if width is None and attr.custom_attribute and attr.min_len is not None:
                width = Decimal(str(attr.min_len))
            return (custom, width is None, width if width is not None else Decimal(0), attr.pk)

        attrs.sort(key=sort_key)
        for index, attr in enumerate(attrs):
            attr.sort_order = (index + 1) * 10
            attr.save(update_fields=["sort_order"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0040_product_ar_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="productattribute",
            name="sort_order",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Менше число — вище в списку. Ставиться автоматично при збереженні товару (за шириною).",
                verbose_name="Порядок",
            ),
        ),
        migrations.AlterModelOptions(
            name="productattribute",
            options={
                "ordering": ["sort_order", "id"],
                "verbose_name": "Варіація",
                "verbose_name_plural": "Варіації",
            },
        ),
        migrations.RunPython(set_initial_sort_order, migrations.RunPython.noop),
    ]
