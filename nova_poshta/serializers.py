from rest_framework.serializers import ModelSerializer
from .models import Settlement, Warehouse


class SettlementSerializer(ModelSerializer):
    class Meta:
        model = Settlement
        fields = "__all__"


class WarehouseSerializer(ModelSerializer):
    class Meta:
        model = Warehouse
        fields = "__all__"