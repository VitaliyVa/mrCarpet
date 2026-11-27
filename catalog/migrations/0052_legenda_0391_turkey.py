"""Legenda 0391 is the Turkish ALBAYRAK 0391 (same number and swirl design on
Rozetka, 27.11.2026), not Ukrainian: country spec and the one sentence in
the description that said «зроблено в Україні».

Idempotent, keyed on the slug, only exact old values change, never raises.
"""

from django.db import migrations

SLUG = "kilim-ovalnii-sinii-legenda-0391"
OLD_TEXT = "зроблено в Україні"
NEW_TEXT = "зроблено в Туреччині"


def forwards(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductSpecification = apps.get_model("catalog", "ProductSpecification")
    SpecificationValue = apps.get_model("catalog", "SpecificationValue")
    changed = 0
    try:
        product = Product.objects.filter(slug=SLUG).first()
        if product is None:
            return
        rows = ProductSpecification.objects.filter(
            product=product,
            specification__title__contains="раїна",  # «Країна-виробник ...»
            spec_value__title="Україна",
        ).select_related("specification")
        for row in rows:
            turkey = (
                SpecificationValue.objects.filter(
                    specification=row.specification, title="Туреччина"
                ).first()
                or SpecificationValue.objects.create(
                    specification=row.specification, title="Туреччина"
                )
            )
            row.spec_value = turkey
            row.save(update_fields=["spec_value"])
            changed += 1
        for field in ("description", "meta_description"):
            value = getattr(product, field, None)
            if value and OLD_TEXT in value:
                setattr(product, field, value.replace(OLD_TEXT, NEW_TEXT))
                product.save(update_fields=[field])
                changed += 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [catalog] legenda 0391 skipped: {exc}")
        return
    print(f"\n  [catalog] legenda 0391 -> Turkey: {changed}")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0051_fix_specs_for_rozetka"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
