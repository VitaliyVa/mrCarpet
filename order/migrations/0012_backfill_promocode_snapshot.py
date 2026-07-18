from django.db import migrations


def backfill_promocode_snapshot(apps, schema_editor):
    Order = apps.get_model("order", "Order")
    for order in Order.objects.filter(promocode_id__isnull=False).select_related(
        "promocode"
    ):
        promo = order.promocode
        if not promo:
            continue
        update = {}
        if not order.promocode_code:
            update["promocode_code"] = promo.code
        if order.promocode_discount is None:
            update["promocode_discount"] = promo.discount
        if update:
            Order.objects.filter(pk=order.pk).update(**update)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("order", "0011_promocode_usage_limits"),
    ]

    operations = [
        migrations.RunPython(backfill_promocode_snapshot, noop_reverse),
    ]
