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
    order = cart.order
    print(order.id)
    total_price = cart.get_total_price()
    liqpay = LiqPay(settings.LIQPAY_PUBLIC_KEY, settings.LIQPAY_PRIVATE_KEY)
    params = {
        'action': 'pay',
        'amount': float(total_price),
        'currency': 'UAH',
        'description': 'Payment for clothes',
        'order_id': str(order.id),
        'version': '3',
        'sandbox': 1,  # sandbox mode, set to 1 to enable it
        'server_url': 'https://mrcarpet.shop/api/pay-callback/',
    }
    signature = liqpay.cnb_signature(params)
    data = liqpay.cnb_data(params)
    print(signature, data)
    return signature, data

def get_liqpay_response(request):
    liqpay = LiqPay(settings.LIQPAY_PUBLIC_KEY, settings.LIQPAY_PRIVATE_KEY)
    signature = request.POST.get("signature")
    data = request.POST.get("data")
    sign = liqpay.str_to_sign(settings.LIQPAY_PRIVATE_KEY + data + settings.LIQPAY_PRIVATE_KEY)
    response = liqpay.decode_data_from_str(data)
    print(response)
    if sign == signature:
        print("callback is valid")
    return response


def create_payment(request, response):
    status = response.get("status")
    order_id = response.get("order_id")
    print(status, order_id)
    if status == "failure":
        return redirect("index")
    order = Order.objects.get(id=int(order_id))
    cart = order.cart
    form = PaymentForm(response)
    payment = form.save(commit=False)
    payment.order = order
    payment.save()
    cart.ordered = True
    cart.save()
    print(cart.id, cart.ordered)
    # recipients = settings.DEFAULT_RECIPIENT_LIST.copy()
    # recipients.append(order.email)
    # send_mail(
    #     subject="Dunlop - оформлення замовлення",
    #     message="Dunlop - оформлення замовлення",
    #     html_message=render_to_string("includes/mail/make_order.html", locals()),
    #     from_email=settings.DEFAULT_FROM_EMAIL,
    #     recipient_list=recipients,
    #     fail_silently=False,
    # )
