from django.contrib import admin
from .models import (
    Product,
    ProductCategory,
    Favourite,
    FavouriteProducts,
    Specification,
    SpecificationValue,
    ProductSpecification,
    Size,
    ProductAttribute,
    ProductReview,
    RelatedProduct,
    ProductSale,
)


# Register your models here.
class FavouriteItemInLine(admin.TabularInline):
    model = FavouriteProducts
    extra = 0


class FavouriteAdmin(admin.ModelAdmin):
    inlines = [FavouriteItemInLine]

    class Meta:
        model = Favourite


class ProductInLine(admin.TabularInline):
    model = ProductAttribute
    extra = 0


class RelatedProductInline(admin.TabularInline):
    model = RelatedProduct
    fk_name = "related_to"
    extra = 0


class SpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 0


class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductInLine, RelatedProductInline, SpecificationInline]

    class Meta:
        model = Product


admin.site.register(Product, ProductAdmin)
admin.site.register(ProductCategory)
admin.site.register(Favourite, FavouriteAdmin)
admin.site.register(Specification)
admin.site.register(SpecificationValue)
admin.site.register(ProductSpecification)
admin.site.register(Size)
admin.site.register(ProductAttribute)
admin.site.register(ProductReview)
admin.site.register(ProductSale)
