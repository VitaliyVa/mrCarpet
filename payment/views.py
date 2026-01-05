from django.shortcuts import render, redirect
from django.contrib import messages

from payment.utils import get_liqpay_context
from cart.utils import get_cart


# Create your views here.
def payment_view(request):
    cart = get_cart(request)
    
    # Перевіряємо, чи є замовлення в корзині
    if not cart.order:
        messages.error(request, "Немає активного замовлення для оплати")
        return redirect("index")
    
    # Перевіряємо, чи замовлення потребує оплати
    if cart.order.payment_type != "liqpay":
        messages.error(request, "Це замовлення не потребує онлайн оплати")
        return redirect("index")
    
    try:
        signature, data = get_liqpay_context(request)
        context = {
            "signature": signature,
            "data": data,
            "order": cart.order
        }
        return render(request, "payment.html", context=context)
    except Exception as e:
        messages.error(request, f"Помилка при створенні платежу: {str(e)}")
        return redirect("index")
