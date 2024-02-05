from django.urls import path, include

from rest_framework.routers import DefaultRouter

from .views import OrderCreateViewSet


router = DefaultRouter()
router.register(r"create-order", OrderCreateViewSet, basename="order")

urlpatterns = [path("", include(router.urls))]
