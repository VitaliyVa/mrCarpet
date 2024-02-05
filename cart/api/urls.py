from django.urls import path, include

from rest_framework.routers import DefaultRouter

from .views import (
    CartProductViewSet,
    # CartViewSet
)

router = DefaultRouter()
router.register(r"cart-products", CartProductViewSet, basename="cart-products")
# router.register(r"carts", CartViewSet, basename="carts")


urlpatterns = [
    path('', include(router.urls))
]