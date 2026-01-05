from rest_framework import serializers

from cart.api.serializers import CartSerializer
from ..models import Order


class OrderSerializer(serializers.ModelSerializer):
    cart = CartSerializer(read_only=True)
    promocode = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email = serializers.CharField(required=False)  # Зробимо опціональним, буде встановлюватись в view

    class Meta:
        model = Order
        exclude = ("total_price", "status", "order_number")
        read_only_fields = ("created", "updated")
    
    def validate_email(self, value):
        """Валідація email, якщо він переданий"""
        if value and '@' not in value:
            raise serializers.ValidationError("Введіть коректний email адрес.")
        return value
