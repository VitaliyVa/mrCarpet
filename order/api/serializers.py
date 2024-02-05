from rest_framework import serializers

from cart.api.serializers import CartSerializer
from ..models import Order


class OrderSerializer(serializers.ModelSerializer):
    cart = CartSerializer(read_only=True)
    class Meta:
        model = Order
        exclude = ("total_price", "status", "order_number",)
