from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0013_alter_order_address_warehouse_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="ga4_mp_sent",
            field=models.BooleanField(
                default=False,
                editable=False,
                help_text="Measurement Protocol purchase already sent (dedupe).",
                verbose_name="GA4 MP purchase надіслано",
            ),
        ),
    ]
