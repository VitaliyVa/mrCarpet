"""Spec fixes after the Rozetka price check (27.11.2026).

- Two oval rugs (title, photo and text say oval) had «Форма килима:
  Прямокутник» -> Овал.
- Oksi 38025.608 had «Висота ворса: Безворсовий», but it is a pile rug
  (photo, own description). The exact height is unknown, so the value is
  cleared (row kept, spec_value=None: the PDP and feeds skip such rows).
- «Основа: Резина» is Russian -> «Гума».

Idempotent, keyed on slugs and titles, no deletions, never raises.
"""

from django.db import migrations

OVAL_SLUGS = (
    "kilim-ovalnii-sirii-moderngk506-o",
    "kilim-ovalnii-bezhevii-la-rosa-gk500",
)
NO_PILE_FIX_SLUGS = ("kilim-priamokutnii-oksi-38025608",)


def forwards(apps, schema_editor):
    ProductSpecification = apps.get_model("catalog", "ProductSpecification")
    SpecificationValue = apps.get_model("catalog", "SpecificationValue")
    changed = 0
    try:
        rows = ProductSpecification.objects.filter(
            product__slug__in=OVAL_SLUGS,
            specification__title__contains="орма",  # SQLite LIKE is case-sensitive for Cyrillic
            spec_value__title="Прямокутник",
        ).select_related("specification")
        for row in rows:
            oval = (
                SpecificationValue.objects.filter(
                    specification=row.specification, title="Овал"
                ).first()
                or SpecificationValue.objects.create(
                    specification=row.specification, title="Овал"
                )
            )
            row.spec_value = oval
            row.save(update_fields=["spec_value"])
            changed += 1

        changed += ProductSpecification.objects.filter(
            product__slug__in=NO_PILE_FIX_SLUGS,
            specification__title__icontains="ворс",
            spec_value__title="Безворсовий",
        ).update(spec_value=None)

        changed += SpecificationValue.objects.filter(
            specification__title="Основа", title="Резина"
        ).update(title="Гума")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [catalog] spec fixes skipped: {exc}")
        return
    print(f"\n  [catalog] spec fixes for rozetka: {changed}")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0050_product_titles_2026_11"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
