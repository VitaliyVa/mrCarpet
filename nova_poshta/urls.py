from django.urls import path
from .views import (
    SettlementsList,
    WarehousesList,
)


urlpatterns = [
    path("settlements/", SettlementsList.as_view(), name="settlements"),
    path("warehouses/", WarehousesList.as_view(), name="warehouses"),
]