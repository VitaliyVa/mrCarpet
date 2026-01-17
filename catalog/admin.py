from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.shortcuts import render
from django.utils.html import format_html
from django.db.models import Sum
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


class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline, ProductInLine, RelatedProductInline, SpecificationInline]
    save_as = True
    list_display = ['title', 'is_new', 'has_discount', 'get_color_display', 'get_total_quantity', 'created', 'updated']
    list_filter = ['is_new', 'has_discount', 'created', 'categories', 'active_color']
    search_fields = ['title', 'description']
    actions = ['update_colors_action', 'duplicate_product_action']
    fieldsets = (
        ('Основна інформація', {
            'fields': ('title', 'slug', 'description', 'image', 'categories', 'is_new')
        }),
        ('Кольори', {
            'fields': ('colors', 'active_color')
        }),
        ('Інше', {
            'fields': ('has_discount',)
        }),
    )
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/update-colors-from-title/',
                self.admin_site.admin_view(self.update_colors_from_title),
                name='catalog_product_update_colors_from_title'
            ),
            path(
                'get-spec-values/',
                self.admin_site.admin_view(self.get_spec_values),
                name='catalog_product_get_spec_values'
            ),
        ]
        return custom_urls + urls
    
    @admin.action(description='Оновити кольори для вибраних товарів')
    def update_colors_action(self, request, queryset):
        """
        Admin action для масового оновлення кольорів вибраних товарів.
        Для кожного вибраного товару шукає товари з однаковим title і додає їх active_color в colors.
        """
        updated_count = 0
        total_colors_added = 0
        
        for product in queryset:
            if not product.title:
                continue
            
            # Шукаємо всі товари з однаковим title (включаючи поточний)
            products_with_same_title = Product.admin_objects.filter(
                title__iexact=product.title
            ).select_related('active_color')
            
            # Збираємо всі унікальні active_color з знайдених товарів
            color_ids = set()
            
            for p in products_with_same_title:
                if p.active_color and p.active_color.id not in color_ids:
                    color_ids.add(p.active_color.id)
            
            if color_ids:
                # Отримуємо об'єкти кольорів
                colors = ProductColor.objects.filter(id__in=color_ids)
                
                # Очищаємо старий список кольорів та додаємо нові
                product.colors.clear()
                product.colors.add(*colors)
                product.save()
                
                updated_count += 1
                total_colors_added += len(color_ids)
        
        if updated_count == 0:
            self.message_user(request, "Немає товарів для оновлення або вони не мають назв.", level='warning')
        else:
            self.message_user(
                request,
                f"Кольори оновлено для {updated_count} товарів. Всього додано {total_colors_added} кольорів.",
                level='success'
            )
    
    @admin.action(description='Копіювати вибрані товари')
    def duplicate_product_action(self, request, queryset):
        """
        Admin action для копіювання товарів.
        Створює повну копію товару з усіма пов'язаними об'єктами та змінює title.
        """
        duplicated_count = 0
        
        for original_product in queryset:
            if not original_product.title:
                continue
            
            # Генеруємо новий title
            base_title = original_product.title
            
            # Перевіряємо чи вже є "(копія)" в назві
            if " (копія" in base_title:
                # Знаходимо номер копії якщо є
                import re
                match = re.search(r' \(копія( (\d+))?\)$', base_title)
                if match:
                    copy_num = match.group(2)  # group(2) - це номер, group(1) - це пробіл+номер
                    if copy_num:
                        # Вже є номер, збільшуємо його
                        new_num = int(copy_num) + 1
                        new_title = re.sub(r' \(копія \d+\)$', f' (копія {new_num})', base_title)
                    else:
                        # Просто "(копія)", додаємо номер 2
                        new_title = base_title.replace(' (копія)', ' (копія 2)')
                else:
                    # Є "копія" але не в такому форматі
                    new_title = f"{base_title} (копія)"
            else:
                new_title = f"{base_title} (копія)"
            
            # Перевіряємо унікальність title (на випадок якщо вже є товар з таким title)
            counter = 2
            while Product.admin_objects.filter(title=new_title).exists():
                if " (копія" in base_title:
                    match = re.search(r' \(копія( (\d+))?\)$', base_title)
                    if match:
                        new_title = re.sub(r' \(копія( \d+)?\)$', f' (копія {counter})', base_title)
                    else:
                        new_title = f"{base_title} (копія {counter})"
                else:
                    new_title = f"{base_title} (копія {counter})"
                counter += 1
            
            # Створюємо копію товару
            # Спочатку зберігаємо ManyToMany зв'язки
            original_categories = list(original_product.categories.all())
            original_colors = list(original_product.colors.all())
            
            # Створюємо новий продукт, копіюючи всі поля крім id та автоматичних
            new_product = Product(
                title=new_title,
                description=original_product.description,
                image=original_product.image,  # Django скопіює посилання на файл
                is_new=original_product.is_new,
                has_discount=original_product.has_discount,
                active_color=original_product.active_color,
                meta_title=original_product.meta_title,
                meta_description=original_product.meta_description,
                meta_keys=original_product.meta_keys,
                # slug буде згенеровано автоматично в save()
                # created та updated будуть автоматично встановлені
            )
            new_product.save()  # Зберігаємо для отримання id
            
            # Копіюємо ManyToMany зв'язки
            new_product.categories.set(original_categories)
            new_product.colors.set(original_colors)
            
            # Копіюємо ProductImage
            for original_image in original_product.images.all():
                ProductImage.objects.create(
                    product=new_product,
                    image=original_image.image,
                    alt=original_image.alt
                )
            
            # Копіюємо ProductAttribute
            for original_attr in original_product.product_attr.all():
                original_widths = list(original_attr.width.all())
                new_attr = ProductAttribute.objects.create(
                    product=new_product,
                    size=original_attr.size,
                    discount=original_attr.discount,
                    price=original_attr.price,
                    quantity=original_attr.quantity,
                    custom_attribute=original_attr.custom_attribute,
                    min_len=original_attr.min_len,
                    max_len=original_attr.max_len,
                    custom_price=original_attr.custom_price
                )
                # Копіюємо ManyToMany width
                new_attr.width.set(original_widths)
            
            # Копіюємо ProductSpecification
            for original_spec in original_product.product_specs.all():
                ProductSpecification.objects.create(
                    product=new_product,
                    specification=original_spec.specification,
                    spec_value=original_spec.spec_value
                )
            
            # Копіюємо RelatedProduct
            # related_to вказує на новий товар, product залишається на оригінальний товар
            for original_related in original_product.related_products.all():
                RelatedProduct.objects.create(
                    related_to=new_product,
                    product=original_related.product
                )
            
            duplicated_count += 1
        
        if duplicated_count == 0:
            self.message_user(request, "Немає товарів для копіювання.", level='warning')
        else:
            self.message_user(
                request,
                f"Створено {duplicated_count} копій товарів.",
                level='success'
            )
    
    def get_color_display(self, obj):
        """Відображає active_color з візуальним індикатором кольору або текстури"""
        if obj.active_color:
            color_title = obj.active_color.title
            # Перевіряємо чи є текстура
            if obj.active_color.texture:
                # Відображаємо текстуру
                return format_html(
                    '<span style="display: inline-flex; align-items: center; gap: 6px;">'
                    '<span style="display: inline-block; width: 16px; height: 16px; background-image: url(\'{}\'); '
                    'background-size: cover; background-position: center; border-radius: 50%; '
                    'border: 1px solid var(--border-color, #ccc); vertical-align: middle; '
                    'box-shadow: 0 0 0 1px rgba(0,0,0,0.1);"></span>'
                    '<span>{}</span>'
                    '</span>',
                    obj.active_color.texture.url,
                    color_title
                )
            elif obj.active_color.color:
                # Відображаємо колір
                color_value = str(obj.active_color.color)
                return format_html(
                    '<span style="display: inline-flex; align-items: center; gap: 6px;">'
                    '<span style="display: inline-block; width: 16px; height: 16px; background-color: {}; '
                    'border-radius: 50%; border: 1px solid var(--border-color, #ccc); '
                    'vertical-align: middle; box-shadow: 0 0 0 1px rgba(0,0,0,0.1);"></span>'
                    '<span>{}</span>'
                    '</span>',
                    color_value,
                    color_title
                )
        return format_html('<span style="color: var(--body-quiet-color, #999);">—</span>')
    
    get_color_display.short_description = 'Колір'
    get_color_display.admin_order_field = 'active_color'
    
    def get_total_quantity(self, obj):
        """Відображає загальну кількість товару з усіх ProductAttribute"""
        total = obj.product_attr.aggregate(total=Sum('quantity'))['total'] or 0
        return total
    
    get_total_quantity.short_description = 'Кількість'
    get_total_quantity.admin_order_field = 'product_attr__quantity'
    
    def update_colors_from_title(self, request, object_id):
        """AJAX view для оновлення кольорів поточного товару на основі title"""
        if request.method != 'POST':
            return JsonResponse({'error': 'Метод не дозволений'}, status=405)
        
        try:
            current_product = Product.admin_objects.get(id=object_id)
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Товар не знайдено'}, status=404)
        
        if not current_product.title:
            return JsonResponse({'error': 'У поточного товару немає назви'}, status=400)
        
        # Шукаємо всі товари з однаковим title (без урахування регістру)
        products = Product.admin_objects.filter(title__iexact=current_product.title).exclude(id=current_product.id).select_related('active_color')
        
        # Збираємо всі унікальні active_color з знайдених товарів
        color_ids = set()
        colors_data = []
        
        for product in products:
            if product.active_color and product.active_color.id not in color_ids:
                color_ids.add(product.active_color.id)
                colors_data.append({
                    'id': product.active_color.id,
                    'title': product.active_color.title,
                    'color': str(product.active_color.color),
                    'slug': product.active_color.slug,
                })
        
        if not color_ids:
            return JsonResponse({
                'success': True,
                'message': 'Товари з такою назвою не знайдено або вони не мають активних кольорів',
                'updated_count': 0,
                'colors_count': 0
            })
        
        # Отримуємо об'єкти кольорів
        colors = ProductColor.objects.filter(id__in=color_ids)
        
        # Очищаємо старий список кольорів та додаємо нові
        current_product.colors.clear()
        current_product.colors.add(*colors)
        current_product.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Кольори оновлено. Додано {len(color_ids)} кольорів',
            'updated_count': len(color_ids),
            'colors_count': len(color_ids),
            'colors': colors_data
        })
    
    def get_spec_values(self, request):
        """AJAX view для отримання значень характеристики"""
        if request.method != 'GET':
            return JsonResponse({'error': 'Метод не дозволений'}, status=405)
        
        spec_id = request.GET.get('specification_id')
        if not spec_id:
            return JsonResponse({'error': 'Не вказано ID характеристики'}, status=400)
        
        try:
            spec_id = int(spec_id)
        except ValueError:
            return JsonResponse({'error': 'Невірний ID характеристики'}, status=400)
        
        # Отримуємо всі значення для цієї характеристики
        values = SpecificationValue.objects.filter(specification_id=spec_id).order_by('title')
        
        values_data = [
            {
                'id': value.id,
                'title': value.title or ''
            }
            for value in values
        ]
        
        return JsonResponse({
            'success': True,
            'values': values_data
        })
    
    def get_queryset(self, request):
        """Використовуємо admin_objects менеджер для показу всіх товарів в адмінці"""
        return self.model.admin_objects.all()

    class Media:
        js = ('admin/js/product_admin.js', 'admin/js/product_specification_inline.js')
        css = {
            'all': ('admin/css/product_admin.css',)
        }

    class Meta:
        model = Product


class ProductColorAdmin(admin.ModelAdmin):
    fields = ["title", "color", "texture"]
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


admin.site.register(Product, ProductAdmin)
admin.site.register(ProductCategory)
admin.site.register(Favourite, FavouriteAdmin)
class SpecificationValueAdmin(admin.ModelAdmin):
    fields = ["specification", "title"]
    list_display = ["title", "specification"]
    list_filter = ["specification"]
    search_fields = ["title"]

admin.site.register(Specification)
admin.site.register(SpecificationValue, SpecificationValueAdmin)
admin.site.register(ProductSpecification)
admin.site.register(Size)
admin.site.register(ProductAttribute)
admin.site.register(ProductReview)
admin.site.register(ProductSale)
admin.site.register(ProductColor, ProductColorAdmin)
admin.site.register(ProductWidth)
admin.site.register(PromoCode)
