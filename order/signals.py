from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Order, PromoCodeRedemption


@receiver(pre_save, sender=Order)
def release_promocode_on_cancel(sender, instance: Order, **kwargs):
    """Скасоване замовлення звільняє слот ліміту промокоду."""
    if not instance.pk:
        return
    try:
        previous = Order.objects.only("status").get(pk=instance.pk)
    except Order.DoesNotExist:
        return
    if (
        previous.status != Order.STATUS_CANCELLED
        and instance.status == Order.STATUS_CANCELLED
    ):
        PromoCodeRedemption.objects.filter(order_id=instance.pk).delete()
