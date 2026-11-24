from django.db.models.signals import post_save, pre_save
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


@receiver(pre_save, sender=Order)
def remember_previous_status(sender, instance: Order, **kwargs):
    """Keep the status before this save for the post_save purchase check."""
    previous = None
    if instance.pk:
        previous = (
            Order.objects.filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )
    instance._status_before_save = previous


@receiver(post_save, sender=Order)
def send_cod_purchase_on_delivery(sender, instance: Order, created, **kwargs):
    """
    Cash on delivery becomes a GA4 `purchase` once the money is real.

    Checkout sends only `order_placed` for cash orders (project/ga4_mp.py),
    because a parcel nobody picks up is not revenue, and Google Ads bids on
    whatever purchase value it is fed. The real purchase goes out here, on
    the first move into paid / completed, with the GA4 ids stored at checkout
    so the sale stays with the session that brought the buyer.

    Card orders are not touched: the LiqPay callback sends theirs.
    Order.ga4_mp_sent dedupes, so orders already reported at creation (the
    old behaviour, or ADS_COD_PURCHASE_STAGE=order) are never sent twice.
    """
    if created or kwargs.get("raw"):
        return
    if instance.payment_type != Order.PAYMENT_CASH or instance.ga4_mp_sent:
        return

    from project.ga4_ecommerce import cod_purchase_stage, order_purchase_is_due

    if cod_purchase_stage() != "delivery" or not order_purchase_is_due(instance):
        return
    before = getattr(instance, "_status_before_save", None)
    if before == instance.status:
        return

    from project.ga4_mp import enqueue_order_purchase_mp

    enqueue_order_purchase_mp(
        instance.pk,
        client_id=instance.ga4_client_id or None,
        session_id=instance.ga4_session_id or None,
    )
