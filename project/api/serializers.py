from rest_framework import serializers

from catalog.models import Product, ProductAttribute

from ..models import ContactRequest, StockInquiry, Subscription


class ContactRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactRequest
        fields = [
            "name",
            "email",
            "text",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    # unique знімаємо: існуючий email реактивує subscribe_email (не create)
    email = serializers.EmailField()

    class Meta:
        model = Subscription
        fields = ["email"]
        extra_kwargs = {
            "email": {"validators": []},
        }


class StockInquirySerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    product_attr_id = serializers.IntegerField(write_only=True, required=True)

    class Meta:
        model = StockInquiry
        fields = [
            "name",
            "email",
            "phone",
            "product_id",
            "product_attr_id",
            "product_title",
            "size_label",
        ]
        extra_kwargs = {
            "product_title": {"required": False, "allow_blank": True},
            "size_label": {"required": False, "allow_blank": True},
        }

    def validate_product_attr_id(self, value):
        if not ProductAttribute.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Варіацію товару не знайдено.")
        return value

    def create(self, validated_data):
        product_id = validated_data.pop("product_id", None)
        product_attr_id = validated_data.pop("product_attr_id")
        product_attr = ProductAttribute.objects.select_related("product", "size").get(
            pk=product_attr_id
        )
        product = product_attr.product
        if product_id:
            product = Product.objects.filter(pk=product_id).first() or product

        validated_data["product"] = product
        validated_data["product_attr"] = product_attr
        if not validated_data.get("product_title"):
            validated_data["product_title"] = product.title
        if not validated_data.get("size_label"):
            validated_data["size_label"] = (
                str(product_attr.size) if product_attr.size else ""
            )
        return super().create(validated_data)
