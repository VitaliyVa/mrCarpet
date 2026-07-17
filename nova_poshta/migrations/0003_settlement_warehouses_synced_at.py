# Generated manually for warehouses resume stamp

from django.db import migrations, models
from django.utils import timezone


def backfill_synced_from_warehouses(apps, schema_editor):
    Settlement = apps.get_model("nova_poshta", "Settlement")
    Warehouse = apps.get_model("nova_poshta", "Warehouse")
    ids = (
        Warehouse.objects.exclude(settlement_id__isnull=True)
        .values_list("settlement_id", flat=True)
        .distinct()
    )
    Settlement.objects.filter(id__in=ids).update(warehouses_synced_at=timezone.now())


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("nova_poshta", "0002_novaposhtasettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="settlement",
            name="warehouses_synced_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="Склади синхронізовано",
            ),
        ),
        migrations.RunPython(backfill_synced_from_warehouses, noop_reverse),
    ]
