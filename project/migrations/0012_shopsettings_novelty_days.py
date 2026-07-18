from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("project", "0011_shopsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopsettings",
            name="novelty_days",
            field=models.PositiveIntegerField(
                default=90,
                help_text=(
                    "Бейдж «Новинка» показується, якщо у товару увімкнено прапорець "
                    "і з дати створення минуло не більше цієї кількості днів."
                ),
                verbose_name="Новинка: днів від створення",
            ),
        ),
    ]
