from django.urls import path, include
from .views import UkrposhtaViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"offices", UkrposhtaViewSet, basename="offices")


urlpatterns = [
    path('', include(router.urls))
]