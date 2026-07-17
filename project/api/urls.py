from django.urls import path

from .views import (
    ContactRequestCreateView,
    StockInquiryCreateView,
    SubscriptionCreateView,
    check_promocode,
)


urlpatterns = [
    path("contact/", ContactRequestCreateView.as_view(), name="contact"),
    path("stock-inquiry/", StockInquiryCreateView.as_view(), name="stock-inquiry"),
    path("subscription/", SubscriptionCreateView.as_view(), name="subscription"),
    path("check-promocode/", check_promocode, name="check_promocode"),
]
