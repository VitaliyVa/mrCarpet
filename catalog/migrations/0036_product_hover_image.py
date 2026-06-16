# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0035_add_specification_to_specificationvalue'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='hover_image',
            field=models.ImageField(
                blank=True,
                max_length=512,
                upload_to='products',
                verbose_name='Зображення при наведенні',
                help_text='Фото для каталогу при наведенні (можна в меншій якості). На детальній сторінці не показується.',
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='image',
            field=models.ImageField(
                blank=True,
                default='products/default.png',
                max_length=512,
                upload_to='products',
                verbose_name='Зображення',
                help_text='Основне фото для каталогу (можна в меншій якості). На детальній сторінці не показується.',
            ),
        ),
    ]
