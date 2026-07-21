from django.db.models.signals import pre_save
from django.utils import timezone
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


@receiver(pre_save, sender=Order)
def stamp_completed_at(sender, instance: Order, **kwargs):
    """
    Record when an order became "Виконано".

    The review invitation counts days from this moment, and `updated` cannot
    serve: it moves on every edit, so correcting a phone number three weeks
    later would push the invitation three weeks further away — forever, if
    anyone kept touching the order.

    Set once. Bouncing the status out of completed and back does not restart
    the clock, because the customer received the rug the first time.
    """
    if not instance.pk:
        if instance.status == Order.STATUS_COMPLETED and not instance.completed_at:
            instance.completed_at = timezone.now()
        return
    try:
        previous = Order.objects.only("status", "completed_at").get(pk=instance.pk)
    except Order.DoesNotExist:
        return
    if (
        instance.status == Order.STATUS_COMPLETED
        and previous.status != Order.STATUS_COMPLETED
        and not previous.completed_at
    ):
        instance.completed_at = timezone.now()
