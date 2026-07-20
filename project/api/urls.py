from django.urls import path

from .meta_webhook import meta_webhook
from .telegram_webhook import telegram_webhook
from .viber_webhook import viber_webhook
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
    path("telegram/webhook/", telegram_webhook, name="telegram-webhook"),
    path("meta/webhook/", meta_webhook, name="meta-webhook"),
    path("viber/webhook/", viber_webhook, name="viber-webhook"),
]
