from django.urls import path

from .meta_webhook import meta_webhook
from .telegram_webhook import telegram_webhook
from .threads_oauth import threads_oauth_callback, threads_oauth_start
from .tiktok_oauth import tiktok_oauth_callback, tiktok_oauth_start
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
    path("tiktok/authorize/", tiktok_oauth_start, name="tiktok-oauth-start"),
    path("tiktok/callback/", tiktok_oauth_callback, name="tiktok-oauth-callback"),
    path("threads/authorize/", threads_oauth_start, name="threads-oauth-start"),
    path("threads/callback/", threads_oauth_callback, name="threads-oauth-callback"),
]
