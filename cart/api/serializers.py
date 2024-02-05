from rest_framework import serializers

from catalog.models import ProductAttribute
from ..models import Cart, CartProduct


class CartProductSerializer(serializers.ModelSerializer):
    product_attr = serializers.PrimaryKeyRelatedField(queryset=ProductAttribute.objects.all())
    cart = serializers.PrimaryKeyRelatedField(queryset=Cart.objects.all())

    class Meta:
        model = CartProduct
        fields = '__all__'


class CartSerializer(serializers.ModelSerializer):
    cart_products = CartProductSerializer(many=True)
    total_price = serializers.SerializerMethodField()
    quantity = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "user",
            "ordered",
            "total_price",
            "quantity",
            "cart_products",
        ]

    def get_total_price(self, obj):
        return obj.get_total_price()

    def get_quantity(self, obj):
        return obj.get_cart_product_total_quantity()