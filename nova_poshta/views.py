from django.db.models import Q, Case, When, IntegerField
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination

from .models import Warehouse, Settlement
from .serializers import (
    WarehouseSerializer,
    SettlementSerializer,
)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class WarehousesList(generics.ListAPIView):
    serializer_class = WarehouseSerializer
    queryset = Warehouse.objects.all()
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        query = self.request.query_params.get("q")

        if not query:
            return Warehouse.objects.none()

        queryset = self.queryset.filter(settlement=query)
        return queryset


class SettlementsList(generics.ListAPIView):
    serializer_class = SettlementSerializer
    queryset = Settlement.objects.all()
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        query = self.request.query_params.get("q")

        if not query:
            return Settlement.objects.none()

        queryset = self.queryset.filter(
            Q(title__iexact=query) | Q(title__istartswith=query) | Q(title__icontains=query)
        ).annotate(
            priority=Case(
                When(title__iexact=query, then=0),
                When(title__istartswith=query, then=1),
                When(title__icontains=query, then=2),
                default=999,
                output_field=IntegerField()
            ),
        ).order_by('priority')
        return queryset