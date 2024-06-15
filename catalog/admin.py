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
    ProductColor,
    ProductWidth,
    PromoCode, ProductImage,
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


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class RelatedProductInline(admin.TabularInline):
    model = RelatedProduct
    fk_name = "related_to"
    extra = 0


class SpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 0


class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline, ProductInLine, RelatedProductInline, SpecificationInline]
    save_as = True

    class Meta:
        model = Product


class ProductColorAdmin(admin.ModelAdmin):
    fields = ["title", "color"]
    list_display = [
        "title",
        "color",
    ]


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
admin.site.register(ProductColor, ProductColorAdmin)
admin.site.register(ProductWidth)
admin.site.register(PromoCode)
