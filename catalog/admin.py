from django.contrib import admin
from .models import Product, ProductCategory, Favourite, FavouriteProducts, Specification, SpecificationValue, ProductSpecification, Size, ProductAttribute

# Register your models here.
class FavouriteItemInLine(admin.TabularInline):
    model = FavouriteProducts
    extra = 0

class FavouriteAdmin(admin.ModelAdmin):
    inlines = [FavouriteItemInLine]
    class Meta:
        model = Favourite


admin.site.register(Product)
admin.site.register(ProductCategory)
admin.site.register(Favourite, FavouriteAdmin)
admin.site.register(Specification)
admin.site.register(SpecificationValue)
admin.site.register(ProductSpecification)
admin.site.register(Size)
admin.site.register(ProductAttribute)