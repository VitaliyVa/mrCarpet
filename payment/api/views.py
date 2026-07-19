import logging

from django.shortcuts import redirect

from ..liqpay_payment import LiqPay

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ..utils import get_liqpay_response, create_payment

logger = logging.getLogger(__name__)


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
