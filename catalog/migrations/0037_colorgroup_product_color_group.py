# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0036_product_hover_image'),
    ]

    operations = [
        migrations.CreateModel(
            name='ColorGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=255, verbose_name='Назва групи')),
            ],
            options={
                'verbose_name': 'Кольорова група',
                'verbose_name_plural': 'Кольорові групи',
            },
        ),
        migrations.AddField(
            model_name='product',
            name='color_group',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='variants',
                to='catalog.colorgroup',
                verbose_name='Кольорова група',
                help_text='Обʼєднує кольорові варіанти одного килима (з різними назвами). Плитки кольорів на сторінці товару беруться з цієї групи.',
            ),
        ),
    ]
