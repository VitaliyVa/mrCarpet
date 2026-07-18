from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0043_product_is_new_help_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="promocode",
            name="max_uses_total",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Порожньо = без ліміту. Наприклад 100 — код помре після 100 замовлень.",
                null=True,
                verbose_name="Макс. використань загалом",
            ),
        ),
        migrations.AddField(
            model_name="promocode",
            name="max_uses_per_user",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Порожньо = без ліміту. 1 = одноразовий на email/акаунт.",
                null=True,
                verbose_name="Макс. використань на користувача",
            ),
        ),
    ]
