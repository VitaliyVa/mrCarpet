"""Inline model admins used by the product and favourite admins."""

from django.contrib import admin
from django.db import models

from catalog.admin_forms import ProductAttributeAdminForm
from catalog.services.product_attr_sort import ordered_size_queryset
from catalog.models import (
    FavouriteProducts,
    ProductAttribute,
    ProductImage,
    ProductSpecification,
    RelatedProduct,
    SpecificationValue,
)

from .widgets import ImagePreviewWidget


class FavouriteItemInLine(admin.TabularInline):
    model = FavouriteProducts
    extra = 0


class ProductInLine(admin.TabularInline):
    model = ProductAttribute
    form = ProductAttributeAdminForm
    extra = 1
    min_num = 1
    validate_min = True
    exclude = ("sort_order",)
    ordering = ("sort_order", "id")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "size":
            kwargs["queryset"] = ordered_size_queryset()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("sort_order", "image", "alt", "is_ai")
    ordering = ("sort_order", "id")
    formfield_overrides = {
        models.ImageField: {"widget": ImagePreviewWidget},
    }


class RelatedProductInline(admin.TabularInline):
    model = RelatedProduct
    fk_name = "related_to"
    extra = 0


class SpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Фільтрація значень характеристики по вибраній характеристиці"""
        if db_field.name == "spec_value":
            # Отримуємо ID вибраної specification з параметрів запиту (для нового рядка)
            # Або з існуючого об'єкта (для редагування)
            spec_id = request.GET.get('specification') or kwargs.get('initial', {}).get('specification')

            if spec_id:
                try:
                    spec_id = int(spec_id)
                    kwargs["queryset"] = SpecificationValue.objects.filter(specification_id=spec_id).order_by('title')
                except (ValueError, TypeError):
                    pass
            else:
                # Якщо характеристика не вибрана - показуємо всі значення
                # (JavaScript буде фільтрувати динамічно)
                kwargs["queryset"] = SpecificationValue.objects.all().order_by('title')

        return super().formfield_for_foreignkey(db_field, request, **kwargs)
