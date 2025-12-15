from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.template.loader import render_to_string

from payment.forms import PaymentForm
from payment.liqpay_payment import LiqPay
from cart.utils import get_cart
from cart.models import Cart
from order.models import Order

import logging


def get_liqpay_context(request):
    cart = get_cart(request)
    
    # Перевіряємо, чи є замовлення
    if not cart.order:
        raise ValueError("Немає замовлення для оплати")
    
    order = cart.order
    total_price = order.total_price
    
    # Перевіряємо, чи є ціна
    if not total_price or total_price <= 0:
        raise ValueError("Невірна сума замовлення")
    
    # Перевіряємо наявність ключів LiqPay
    if not settings.LIQPAY_PUBLIC_KEY or not settings.LIQPAY_PRIVATE_KEY:
        raise ValueError("LiqPay ключі не налаштовані")
    
    liqpay = LiqPay(settings.LIQPAY_PUBLIC_KEY, settings.LIQPAY_PRIVATE_KEY)
    
    # Формуємо опис замовлення
    description = f"Оплата замовлення №{order.order_number}"
    
    # Отримуємо URL для callback (використовуємо request для отримання домену)
    from django.urls import reverse
    server_url = request.build_absolute_uri(reverse('pay_callback'))
    
    params = {
        'action': 'pay',
        'amount': float(total_price),
        'currency': 'UAH',
        'description': description,
        'order_id': str(order.id),
        'version': '3',
        'sandbox': 1 if settings.DEBUG else 0,  # sandbox mode тільки в режимі розробки
        'server_url': server_url,
        'result_url': request.build_absolute_uri('/success/'),  # URL після успішної оплати
    }
    
    signature = liqpay.cnb_signature(params)
    data = liqpay.cnb_data(params)
    
    return signature, data

def get_liqpay_response(request):
    """
    Отримує та перевіряє відповідь від LiqPay
    """
    if not settings.LIQPAY_PUBLIC_KEY or not settings.LIQPAY_PRIVATE_KEY:
        raise ValueError("LiqPay ключі не налаштовані")
    
    liqpay = LiqPay(settings.LIQPAY_PUBLIC_KEY, settings.LIQPAY_PRIVATE_KEY)
    signature = request.POST.get("signature")
    data = request.POST.get("data")
    
    if not signature or not data:
        raise ValueError("Відсутні дані від LiqPay")
    
    # Декодуємо дані
    try:
        response = liqpay.decode_data_from_str(data, signature)
    except Exception as e:
        raise ValueError(f"Помилка декодування даних від LiqPay: {str(e)}")
    
    return response


def create_payment(request, response):
    """
    Створює запис про оплату на основі відповіді від LiqPay
    """
    status = response.get("status")
    order_id = response.get("order_id")
    
    if not order_id:
        raise ValueError("Відсутній ID замовлення в відповіді від LiqPay")
    
    try:
        order = Order.objects.get(id=int(order_id))
    except Order.DoesNotExist:
        raise ValueError(f"Замовлення з ID {order_id} не знайдено")
    
    # Створюємо запис про оплату
    form = PaymentForm(response)
    payment = form.save(commit=False)
    payment.order = order
    payment.save()
    
    # Оновлюємо статус замовлення та корзини
    cart = order.cart
    
    if status == "success":
        order.status = "Комплектується"  # Змінюємо статус на "Комплектується" після успішної оплати
        cart.ordered = True
    elif status == "failure":
        order.status = "Не оплачено"
    elif status == "sandbox":
        # В sandbox режимі також вважаємо оплату успішною
        order.status = "Комплектується"
        cart.ordered = True
    
    order.save()
    cart.save()
    
    return payment
