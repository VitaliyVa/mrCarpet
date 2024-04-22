from rest_framework import serializers

from cart.api.serializers import CartSerializer
from ..models import Order


class OrderSerializer(serializers.ModelSerializer):
    cart = CartSerializer(read_only=True)
    promocode = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Order
        exclude = ("total_price", "status", "order_number")
        read_only_fields = ("created", "updated")
