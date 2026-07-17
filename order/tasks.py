from celery import shared_task

from order.models import Order


@shared_task
def remove_orders():
    """Видаляє неоплачені онлайн-замовлення (очікують оплати)."""
    Order.objects.filter(status=Order.STATUS_AWAITING_PAYMENT).delete()
