from django.urls import path

from .views import ContactRequestCreateView, SubscriptionCreateView


urlpatterns = [
    path('contact/', ContactRequestCreateView.as_view(), name="contact"),
    path('subscription/', SubscriptionCreateView.as_view(), name="subscription")
]