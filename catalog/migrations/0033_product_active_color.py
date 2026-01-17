# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0032_productsale_main_sale'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='active_color',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='active_products',
                to='catalog.productcolor',
                verbose_name='Активний колір'
            ),
        ),
    ]
