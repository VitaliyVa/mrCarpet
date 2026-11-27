from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0021_order_rozetka_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='ttn',
            field=models.CharField(blank=True, default='', help_text="Номер накладної Нової Пошти. Для замовлень з Rozetka обов'язковий при статусі «Відправлено»: його отримає Rozetka, і далі посилку вона відстежує сама.", max_length=64, verbose_name='ТТН'),
        ),
    ]
