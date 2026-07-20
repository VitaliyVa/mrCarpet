from django.urls import path

from .views import pay_callback, payment_status


urlpatterns = [
    path("pay-callback/", pay_callback, name="pay_callback"),
    path("payment-status/", payment_status, name="payment_status"),
]
