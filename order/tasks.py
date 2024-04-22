from celery import shared_task

from order.models import Order


@shared_task
def remove_orders():
    orders = Order.objects.filter(status="Не оплачено")
    orders.delete()
