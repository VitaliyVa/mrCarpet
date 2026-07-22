"""Smaller catalog admins: favourites, colors, categories, specs, reviews, promos."""

from django.contrib import admin
from django.db import models
from django.utils.html import format_html

from catalog.services.product_attr_sort import ordered_size_queryset
from catalog.models import (
    Favourite,
    ProductCategory,
    Specification,
    SpecificationValue,
    ProductSpecification,
    Size,
    ProductAttribute,
    ProductReview,
    ProductSale,
    ProductColor,
    ProductWidth,
    PromoCode,
    ColorGroup,
)

from .widgets import ImagePreviewWidget
from .inlines import FavouriteItemInLine


class FavouriteAdmin(admin.ModelAdmin):
    inlines = [FavouriteItemInLine]

    class Meta:
        model = Favourite


class ProductColorAdmin(admin.ModelAdmin):
    fields = ["title", "color", "texture"]
    formfield_overrides = {
        models.ImageField: {"widget": ImagePreviewWidget},
    }

    class Media:
        js = ('admin/js/texture_paste.js',)
    list_display = [
        "title",
        "color",
        "get_texture_display",
    ]

    def get_texture_display(self, obj):
        """Відображає мініатюру текстури або '—' якщо немає"""
        if obj.texture:
            return format_html('<img src="{}" width="30" height="30" style="border-radius: 50%; object-fit: cover;" />', obj.texture.url)
        return format_html('<span style="color: #999;">—</span>')

    get_texture_display.short_description = 'Текстура'

    def save_model(self, request, obj, form, change):
        # Перевіряємо чи title не порожній
        if not obj.title or obj.title.strip() == '':
            # Якщо title порожній, встановлюємо його на основі кольору або текстури
            if obj.color:
                obj.title = f"Колір {str(obj.color)}"
            elif obj.texture:
                obj.title = "Текстура"
            else:
                obj.title = "Без назви"
        super().save_model(request, obj, form, change)


class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug']
    search_fields = ['title', 'slug', 'meta_title']
    exclude = ['slug']
    fieldsets = (
        ('Основне', {
            'fields': ('title', 'image'),
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description', 'meta_keys'),
            'description': (
                'Мета-теги категорії. Якщо порожньо — у <title> буде назва категорії. '
                'Description: ~150–160 символів, як відповідь на інтент.'
            ),
        }),
    )


class SpecificationValueAdmin(admin.ModelAdmin):
    fields = ["specification", "title"]
    list_display = ["title", "specification"]
    list_filter = ["specification"]
    search_fields = ["title"]


class SizeAdmin(admin.ModelAdmin):
    search_fields = ["title"]

    def get_queryset(self, request):
        return ordered_size_queryset(super().get_queryset(request))


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    """
    Moderation queue first: pending reviews are the only ones needing action,
    so the default view is filtered to them and approving is a bulk action.
    """

    list_display = (
        "created",
        "product",
        "rating",
        "name",
        "status",
        "verified_purchase",
        "short_content",
    )
    list_filter = ("status", "rating", "verified_purchase")
    search_fields = ("name", "email", "content", "product__title")
    list_select_related = ("product",)
    readonly_fields = ("created", "updated", "ip_address", "verified_purchase")
    actions = ("approve_reviews", "reject_reviews")
    list_per_page = 50

    @admin.display(description="Коментар")
    def short_content(self, obj):
        text = (obj.content or "").strip()
        return (text[:70] + "…") if len(text) > 70 else (text or "—")

    @admin.action(description="Опублікувати відгук")
    def approve_reviews(self, request, queryset):
        updated = queryset.update(status=ProductReview.Status.APPROVED)
        self.message_user(request, f"Опубліковано: {updated}")

    @admin.action(description="Відхилити відгук")
    def reject_reviews(self, request, queryset):
        updated = queryset.update(status=ProductReview.Status.REJECTED)
        self.message_user(request, f"Відхилено: {updated}")


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount",
        "end_time",
        "max_uses_total",
        "max_uses_per_user",
        "uses_display",
        "is_active_display",
    )
    list_filter = ("end_time",)
    search_fields = ("code",)
    ordering = ("-created",)
    fieldsets = (
        (
            None,
            {
                "fields": ("code", "discount", "end_time"),
                "description": (
                    "Дата закінчення порожня = без терміну. "
                    "Ліміти використань — окремо нижче; можна комбінувати."
                ),
            },
        ),
        (
            "Ліміти використань",
            {
                "fields": ("max_uses_total", "max_uses_per_user"),
                "description": (
                    "Порожнє поле = без ліміту. "
                    "«На користувача = 1» — одноразовий код на email/акаунт."
                ),
            },
        ),
    )

    @admin.display(description="Використано")
    def uses_display(self, obj):
        used = obj.uses_count()
        if obj.max_uses_total is not None:
            return f"{used} / {obj.max_uses_total}"
        return str(used)

    @admin.display(description="Активний", boolean=True)
    def is_active_display(self, obj):
        return obj.is_active


class ColorGroupAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'get_variants_count']
    search_fields = ['name', 'variants__title']

    def get_variants_count(self, obj):
        return obj.variants.count()
    get_variants_count.short_description = 'Кількість варіантів'


admin.site.register(Favourite, FavouriteAdmin)
admin.site.register(ProductCategory, ProductCategoryAdmin)
admin.site.register(Specification)
admin.site.register(SpecificationValue, SpecificationValueAdmin)
admin.site.register(ProductSpecification)
admin.site.register(Size, SizeAdmin)
admin.site.register(ProductAttribute)
admin.site.register(ProductSale)
admin.site.register(ProductColor, ProductColorAdmin)
admin.site.register(ProductWidth)
admin.site.register(ColorGroup, ColorGroupAdmin)
