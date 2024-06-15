from rest_framework import serializers
from ..models import Product, ProductCategory, Favourite, FavouriteProducts, ProductAttribute, ProductReview, ProductSale
from ..utils import get_favourite


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = [
            'title'
        ]


class ProductAttributeSerializer(serializers.ModelSerializer):
    # old_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductAttribute
        fields = '__all__'

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if representation["discount"]:
            representation["discount"] = f"{instance.discount}%"
            representation["old_price"] = f"{instance.price} грн"
            representation["new_price"] = f"{instance.get_total_price()} грн"
        return representation


class ProductSerializer(serializers.ModelSerializer):
    categories = ProductCategorySerializer(many=True)
    product_attributes = ProductAttributeSerializer(source='product_attr', read_only=True, many=True)
    image_url = serializers.CharField(source="image.url", read_only=True)
    href = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id',
            'title',
            'image_url',
            'href',
            'categories',
            # 'quantity',
            'product_attributes'
        ]

    def get_href(self, obj):
        return obj.get_absolute_url()


    # def to_representation(self, instance):
    #     representation = super().to_representation(instance)
    #     prices = [obj.get_total_price() for obj in instance.product_attr.all() if not obj.custom_attribute]
    #     print(prices)
    #     if prices:
    #         representation["min_price"] = f"{min(prices)} грн"
    #     else:
    #         representation["min_price"] = "Немає фіксованої ціни."
    #     return representation


class FavouriteSerializer(serializers.ModelSerializer):
    product = ProductSerializer(many=True)
    quantity = serializers.SerializerMethodField()

    class Meta:
        model = Favourite
        fields = [
            'id',
            'product',
            'user',
            'quantity',
        ]

    def get_quantity(self, obj):
        return len(obj.product.all())


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


class ProductReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductReview
        fields = "__all__"
        
        
class ProductSaleSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = ProductSale
        fields = [
            "id",
            "date_end",
        ]
        
        
class ProductSaleDetailSerializer(serializers.ModelSerializer):
    products = ProductSerializer(read_only=True, many=True)
    
    class Meta:
        model = ProductSale
        fields = [
            "id",
            "date_end",
            "products"
        ]
        
        
class SaleSerializer(serializers.Serializer):
    main_sale_date = serializers.SerializerMethodField()
    sales = serializers.SerializerMethodField()
    
    def get_main_sale_date(self, obj):
        try:
            main_sale = ProductSale.objects.get(main_sale=True)
            return main_sale.date_end
        except ProductSale.DoesNotExist:
            return "Немає головного розпродажу"
        
    def get_sales(self, obj):
        sales = ProductSale.objects.all()
        return ProductSaleSerializer(sales, many=True).data
