from django.urls import path
from .views import payment_view


urlpatterns = [
    path('payment/', payment_view, name="payment"),
]
