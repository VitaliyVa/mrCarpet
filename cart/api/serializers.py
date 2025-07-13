from rest_framework import serializers

from catalog.models import ProductAttribute, ProductWidth
from ..models import Cart, CartProduct


class ProductWidthSerializer(serializers.ModelSerializer):
    def get_choices(self):
        return [value.width for value in ProductWidth.objects.all()]
    class Meta:
        model = ProductWidth
        fields = ["width"]


class CartProductSerializer(serializers.ModelSerializer):
    product_attr = serializers.PrimaryKeyRelatedField(
        queryset=ProductAttribute.objects.all()
    )
    cart = serializers.PrimaryKeyRelatedField(queryset=Cart.objects.all())
    width = serializers.PrimaryKeyRelatedField(queryset=ProductWidth.objects.all(), write_only=True, required=False)
    length = serializers.DecimalField(max_digits=5, decimal_places=1, write_only=True, required=False)
    total_price = serializers.SerializerMethodField()
    # quantity = serializers.CharField()

    class Meta:
        model = CartProduct
        fields = "__all__"

    def get_total_price(self, obj):
        try:
            if obj.total_price is not None:
                return f"{obj.total_price} грн"
            else:
                return f"{obj.cart_product_total_price()} грн"
        except (TypeError, ValueError):
            return "0 грн"


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
        return f"{obj.get_total_price()} грн."

    def get_quantity(self, obj):
        return obj.get_cart_product_total_quantity()
