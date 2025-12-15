from django.shortcuts import redirect

from ..liqpay_payment import LiqPay

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ..utils import get_liqpay_response, create_payment


@csrf_exempt
@api_view(['POST'])
def pay_callback(request):
    """
    Callback endpoint для отримання результатів оплати від LiqPay
    """
    try:
        response = get_liqpay_response(request)
        payment = create_payment(request, response)
        
        status = response.get("status")
        
        # Повертаємо успішну відповідь для LiqPay
        if status in ["success", "sandbox"]:
            return JsonResponse({"status": "ok"})
        else:
            return JsonResponse({"status": "error", "message": "Payment failed"})
            
    except Exception as e:
        # Логуємо помилку
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Помилка в pay_callback: {str(e)}")
        
        # Повертаємо помилку для LiqPay
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
