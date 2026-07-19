from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0012_backfill_promocode_snapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="address",
            field=models.CharField(
                blank=True,
                help_text="Назва відділення / поштомату Нової Пошти",
                max_length=512,
                null=True,
                verbose_name="Відділення НП",
            ),
        ),
    ]
