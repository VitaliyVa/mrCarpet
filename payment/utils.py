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
    import logging
    logger = logging.getLogger(__name__)
    
    # Формуємо абсолютний URL для webhook
    # URL має бути: /api/pay-callback/ (оскільки payment.api.urls підключено через path('api/', ...))
    # ВАЖЛИВО: LiqPay вимагає HTTPS для webhook URL
    try:
        # Отримуємо шлях до callback
        callback_path = reverse('pay_callback')  # Поверне: /api/pay-callback/
        
        # Формуємо повний абсолютний URL
        server_url = request.build_absolute_uri(callback_path)
        
        # Переконаємося, що використовується HTTPS (LiqPay вимагає HTTPS для webhook)
        if server_url.startswith('http://'):
            server_url = server_url.replace('http://', 'https://', 1)
            logger.warning(f"Змінено протокол на HTTPS для webhook URL")
            print(f"[PAYMENT] УВАГА: Змінено протокол на HTTPS для webhook URL")
        
        logger.info(f"Webhook URL для LiqPay: {server_url}")
        logger.info(f"Callback path: {callback_path}")
        print(f"[PAYMENT] Webhook URL для LiqPay: {server_url}")
        print(f"[PAYMENT] Callback path: {callback_path}")
        print(f"[PAYMENT] Повний URL буде відправлено в LiqPay: {server_url}")
    except Exception as e:
        logger.error(f"Помилка при формуванні webhook URL: {str(e)}")
        # Fallback - використовуємо прямий шлях з HTTPS
        server_url = request.build_absolute_uri('/api/pay-callback/')
        if server_url.startswith('http://'):
            server_url = server_url.replace('http://', 'https://', 1)
        logger.warning(f"Використовуємо fallback URL: {server_url}")
        print(f"[PAYMENT] Fallback webhook URL: {server_url}")
    
    # Формуємо result_url (також має бути HTTPS)
    result_url = request.build_absolute_uri('/success/')
    if result_url.startswith('http://'):
        result_url = result_url.replace('http://', 'https://', 1)
    
    params = {
        'action': 'pay',
        'amount': float(total_price),
        'currency': 'UAH',
        'description': description,
        'order_id': str(order.id),
        'version': '3',
        'sandbox': 1 if settings.DEBUG else 0,  # sandbox mode тільки в режимі розробки
        'server_url': server_url,
        'result_url': result_url,  # URL після успішної оплати (також має бути HTTPS)
    }
    
    # Логуємо параметри для діагностики
    logger.info(f"Параметри платежу LiqPay: {params}")
    print("=" * 50)
    print("[PAYMENT] Параметри платежу LiqPay:")
    print(f"  action: {params['action']}")
    print(f"  amount: {params['amount']}")
    print(f"  currency: {params['currency']}")
    print(f"  description: {params['description']}")
    print(f"  order_id: {params['order_id']}")
    print(f"  version: {params['version']}")
    print(f"  sandbox: {params['sandbox']}")
    print(f"  server_url: {params['server_url']}")
    print(f"  result_url: {params['result_url']}")
    print(f"  Public Key: {settings.LIQPAY_PUBLIC_KEY[:10]}..." if settings.LIQPAY_PUBLIC_KEY else "  Public Key: НЕ ВСТАНОВЛЕНО")
    print("=" * 50)
    
    signature = liqpay.cnb_signature(params)
    data = liqpay.cnb_data(params)
    
    logger.info(f"Signature: {signature[:20]}...")
    logger.info(f"Data length: {len(data)}")
    print(f"[PAYMENT] Signature (first 20 chars): {signature[:20]}...")
    print(f"[PAYMENT] Data length: {len(data)}")
    
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
    
    # Логуємо для діагностики
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Отримано signature: {signature}")
    logger.info(f"Отримано data (first 50 chars): {data[:50]}...")
    print(f"[PAYMENT] Отримано signature: {signature}")
    print(f"[PAYMENT] Отримано data (first 50 chars): {data[:50]}...")
    
    # Декодуємо дані
    try:
        response = liqpay.decode_data_from_str(data, signature)
        logger.info(f"Декодована відповідь: {response}")
        print(f"[PAYMENT] Декодована відповідь: {response}")
    except Exception as e:
        logger.error(f"Помилка декодування: {str(e)}")
        print(f"[PAYMENT] Помилка декодування: {str(e)}")
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
        order.status = "Комплектується, оплачено"  # Змінюємо статус на "Комплектується, оплачено" після успішної оплати
        cart.ordered = True
    elif status == "failure":
        order.status = "Не оплачено"
    elif status == "sandbox":
        # В sandbox режимі також вважаємо оплату успішною
        order.status = "Комплектується, оплачено"
        cart.ordered = True
    
    order.save()
    cart.save()
    
    return payment
