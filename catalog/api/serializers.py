from rest_framework import serializers
from ..models import Product, ProductCategory, Favourite, FavouriteProducts, ProductAttribute


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = [
            'title'
        ]


class ProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttribute
        fields = '__all__'


class ProductSerializer(serializers.ModelSerializer):
    categories = ProductCategorySerializer(many=True)
    product_attributes = ProductAttributeSerializer(source='product_attr', read_only=True, many=True)
    class Meta:
        model = Product
        fields = [
            'id',
            'title',
            'image',
            'categories',
            'quantity',
            'product_attributes'
        ]


class FavouriteSerializer(serializers.ModelSerializer):
    product = ProductSerializer(many=True)
    class Meta:
        model = Favourite
        fields = [
            'id',
            'product',
            'user'
        ]


class FavouriteProductsSerializer(serializers.ModelSerializer):
    # user = serializers.PrimaryKeyRelatedField(source='')
    class Meta:
        model = FavouriteProducts
        fields = [
            # 'user',
            'id',
            'favourite',
            'product',
        ]