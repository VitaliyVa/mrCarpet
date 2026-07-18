from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0009_order_status_city_email_admin"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="free_shipping",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Доставка за рахунок магазину (поріг на момент оформлення).",
                verbose_name="Безкоштовна доставка",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="free_shipping_threshold",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Який поріг діяв, коли замовлення отримало безкоштовну доставку.",
                null=True,
                verbose_name="Поріг безкоштовної доставки (грн)",
            ),
        ),
    ]
