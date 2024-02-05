from django.urls import path

from .views import ContactRequestCreateView


urlpatterns = [
    path('contact/', ContactRequestCreateView.as_view(), name="contact")
]