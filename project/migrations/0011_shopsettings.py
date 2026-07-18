from django.db import migrations, models


def create_default_shop_settings(apps, schema_editor):
    ShopSettings = apps.get_model("project", "ShopSettings")
    if not ShopSettings.objects.exists():
        ShopSettings.objects.create(
            pk=1,
            free_shipping_enabled=True,
            free_shipping_threshold=800,
            delivery_from_price=90,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("project", "0010_telegramsettings_scout_default"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShopSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "free_shipping_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Вимкни — опція зникне з кошика, карток товару й нових замовлень.",
                        verbose_name="Безкоштовна доставка увімкнена",
                    ),
                ),
                (
                    "free_shipping_threshold",
                    models.PositiveIntegerField(
                        default=800,
                        help_text="Сума товарів (після промокоду), від якої доставка за наш рахунок.",
                        verbose_name="Поріг безкоштовної доставки (грн)",
                    ),
                ),
                (
                    "delivery_from_price",
                    models.PositiveIntegerField(
                        default=90,
                        help_text="Показується як «Від X грн» і перекреслюється при безкоштовній доставці.",
                        verbose_name="Мін. тариф доставки для UI (грн)",
                    ),
                ),
            ],
            options={
                "verbose_name": "Налаштування магазину",
                "verbose_name_plural": "Налаштування магазину",
            },
        ),
        migrations.RunPython(create_default_shop_settings, noop_reverse),
    ]
