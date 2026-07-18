from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0044_promocode_usage_limits"),
    ]

    operations = [
        migrations.AlterField(
            model_name="promocode",
            name="end_time",
            field=models.DateTimeField(
                blank=True,
                help_text="Порожньо = без терміну дії (діє необмежено в часі).",
                null=True,
                verbose_name="Дата закінчення",
            ),
        ),
    ]
