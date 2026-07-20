import logging

from django.shortcuts import redirect

from ..liqpay_payment import LiqPay

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ..utils import get_liqpay_response, create_payment

logger = logging.getLogger(__name__)


@api_view(['GET'])
def payment_status(request):
    """Статус оплати замовлення, що зараз оплачується (поллінг з /payment/).

    Потрібен, бо LiqPay-віджет не завжди віддає `liqpay.callback`: якщо
    покупець закриває вікно 3D Secure вручну, віджет зависає на «Apply»,
    хоча webhook у нас уже відпрацював і замовлення оплачене.
    Джерело правди — наша БД, а не подія віджета.

    Id замовлення береться ЛИШЕ з сесії (кладеться у payment_view), тож
    чужий статус подивитись не можна. Кошик тут свідомо не чіпаємо:
    get_cart() створює новий Cart на кожен виклик і після оплати
    (cart.ordered=True) віддав би порожній кошик замість оплаченого.
    """
    from order.models import Order

    order_id = request.session.get('pending_payment_order_id')
    if not order_id:
        return JsonResponse({'status': None, 'paid': False})

    order = Order.objects.filter(pk=order_id).only('status', 'order_number').first()
    if not order:
        return JsonResponse({'status': None, 'paid': False})

    paid = order.status in (
        Order.STATUS_PAID, Order.STATUS_SHIPPED, Order.STATUS_COMPLETED,
    )
    return JsonResponse({'status': order.status, 'paid': paid})


@csrf_exempt
@api_view(['POST'])
def pay_callback(request):
    """
    Callback endpoint для отримання результатів оплати від LiqPay
    Webhook URL: /api/pay-callback/
    """
    logger.info("=== WEBHOOK ОТРИМАНО ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"POST data: {request.POST}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Remote address: {request.META.get('REMOTE_ADDR')}")
    
    try:
        response = get_liqpay_response(request)
        logger.info(f"Декодована відповідь від LiqPay: {response}")
        
        payment = create_payment(request, response)
        logger.info(f"Створено платіж: {payment.id} для замовлення: {payment.order.id}")
        
        status = response.get("status")
        logger.info(f"Статус оплати: {status}")
        
        # Повертаємо успішну відповідь для LiqPay
        if status in ["success", "sandbox"]:
            logger.info("Оплата успішна, повертаємо ok")
            return JsonResponse({"status": "ok"})
        else:
            logger.warning(f"Оплата не успішна, статус: {status}")
            return JsonResponse({"status": "error", "message": "Payment failed"})
            
    except Exception as e:
        # Логуємо помилку
        logger.error(f"Помилка в pay_callback: {str(e)}", exc_info=True)
        
        # Повертаємо помилку для LiqPay
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
