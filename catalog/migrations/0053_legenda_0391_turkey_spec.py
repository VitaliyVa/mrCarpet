"""Follow-up to 0052: the country lives in the «Виробник» spec (values
«Україна» / «Турція») and in the country categories, not in a «Країна» spec.
Legenda 0391 (= ALBAYRAK 0391): Виробник -> Турція, category Українські ->
Турецькі.

Idempotent, keyed on slug and titles, never raises.
"""

from django.db import migrations

SLUG = "kilim-ovalnii-sinii-legenda-0391"


def forwards(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductCategory = apps.get_model("catalog", "ProductCategory")
    ProductSpecification = apps.get_model("catalog", "ProductSpecification")
    SpecificationValue = apps.get_model("catalog", "SpecificationValue")
    changed = 0
    try:
        product = Product.objects.filter(slug=SLUG).first()
        if product is None:
            return
        for row in ProductSpecification.objects.filter(
            product=product, specification__title="Виробник", spec_value__title="Україна"
        ).select_related("specification"):
            turkey = (
                SpecificationValue.objects.filter(
                    specification=row.specification, title="Турція"
                ).first()
                or SpecificationValue.objects.create(
                    specification=row.specification, title="Турція"
                )
            )
            row.spec_value = turkey
            row.save(update_fields=["spec_value"])
            changed += 1
        ukrainian = ProductCategory.objects.filter(title="Українські").first()
        turkish = ProductCategory.objects.filter(title="Турецькі").first()
        if ukrainian and turkish and product.categories.filter(pk=ukrainian.pk).exists():
            product.categories.add(turkish)
            product.categories.remove(ukrainian)
            changed += 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [catalog] legenda 0391 spec skipped: {exc}")
        return
    print(f"\n  [catalog] legenda 0391 spec/category -> Turkey: {changed}")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0052_legenda_0391_turkey"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
