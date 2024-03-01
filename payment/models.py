from django.db import models


class Payment(models.Model):
    order               = models.OneToOneField(verbose_name='Замовлення', to='order.Order', on_delete=models.CASCADE, blank=True, null=True)
    timestamp           = models.DateTimeField(verbose_name='Час', auto_now_add=True, blank=True, null=True)
    status              = models.CharField(verbose_name='Статус', max_length=255, blank=True, null=True)
    ip                  = models.CharField(verbose_name='ІР', max_length=255, blank=True, null=True)
    amount              = models.CharField(verbose_name='Сумма', max_length=255, blank=True, null=True)
    currency            = models.CharField(verbose_name='Валюта', max_length=255, blank=True, null=True)
    sender_phone        = models.CharField(verbose_name='Номер телефону', max_length=255, blank=True, null=True)
    sender_first_name   = models.CharField(verbose_name='Імя', max_length=255, blank=True, null=True)
    sender_last_name    = models.CharField(verbose_name='Прізвище', max_length=255, blank=True, null=True)
    sender_card_mask2   = models.CharField(verbose_name='Номер карти', max_length=255, blank=True, null=True)
    sender_card_bank    = models.CharField(verbose_name='Банк', max_length=255, blank=True, null=True)
    sender_card_type    = models.CharField(verbose_name='Тип карти', max_length=255, blank=True, null=True)
    sender_card_country = models.CharField(verbose_name='Країна', max_length=255, blank=True, null=True)

    def __str__(self):
        return f'{self.order}|{self.amount}|{self.currency}'

    class Meta:
        verbose_name = 'Оплата'
        verbose_name_plural = 'Оплати'
