"""Product admin: the catalog's main admin, with image/AR/SEO generation."""

import base64
import os
import shutil
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.db.models import Sum
from django.http import JsonResponse
from django.urls import path
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from catalog.services.replicate_product_images import (
    ReplicateGenerationError,
    ReplicateProductImageService,
)
from catalog.services.replicate_prompt_options import GenerationOptions
from catalog.services.scene_size import SceneSizeError, resolve_scene_size
from catalog.admin_forms import ProductAdminForm
from catalog.services.ar_texture import ArTextureService, mark_ar_ready_from_manual_upload
from catalog.services.product_attr_sort import reorder_product_attributes
from catalog.tasks import generate_ar_texture_task, generate_seo_batch_task
from catalog.models import (
    Product,
    ProductAttribute,
    ProductColor,
    ProductImage,
    ProductSpecification,
    RelatedProduct,
    SpecificationValue,
    ColorGroup,
)

from .widgets import ColorSelectWidget, ImagePreviewWidget
from .inlines import (
    ProductImageInline,
    ProductInLine,
    RelatedProductInline,
    SpecificationInline,
)


class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    inlines = [ProductImageInline, ProductInLine, RelatedProductInline, SpecificationInline]
    formfield_overrides = {
        models.ImageField: {"widget": ImagePreviewWidget},
    }
    save_as = True
    list_display = ['title', 'is_new', 'has_discount', 'get_ar_status_display_col', 'get_color_display', 'get_color_group_display', 'get_total_quantity', 'created', 'updated']
    list_filter = ['is_new', 'has_discount', 'ar_status', 'created', 'categories', 'active_color', 'color_group']
    list_select_related = ('active_color', 'color_group')
    search_fields = ['title', 'description']
    actions = [
        'group_color_variants_action',
        'ungroup_color_variants_action',
        'duplicate_product_action',
        'generate_ar_texture_action',
        'generate_seo_action',
        'publish_to_all_socials',
    ]
    readonly_fields = ['ar_status', 'ar_error', 'ar_updated_at', 'ar_texture_preview']
    fieldsets = (
        ('Основна інформація', {
            'fields': ('title', 'slug', 'description')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description', 'meta_keys'),
            'description': (
                '<button type="button" class="button" id="seo-generate-btn">'
                'Згенерувати SEO з фото (gpt-4o-mini)</button>'
                '<span id="seo-generate-status" style="margin-left:10px;"></span>'
                '<br><small>Бере каталожне фото + розміри/характеристики товару. '
                'Якщо Description порожній — також згенерує короткий опис для PDP.</small>'
            ),
        }),
        ('Зображення та категорії', {
            'fields': ('image', 'hover_image', 'categories', 'is_new'),
            'description': (
                "«Новинка» на сайті = галочка + вікно днів від створення "
                "(див. Налаштування магазину, за замовчуванням 90 днів)."
            ),
        }),
        ('Кольори', {
            'fields': ('active_color', 'color_group'),
            'description': (
                '<b>Як звʼязати кольори килима:</b><br>'
                '1) Створіть кожен кольоровий варіант як <b>окремий товар</b> і задайте йому '
                '«Активний колір» (назви товарів можуть бути різними — це більше не важливо).<br>'
                '2) У списку товарів виділіть ці варіанти та застосуйте дію '
                '<b>«Обʼєднати вибрані в кольорову групу»</b> (або вкажіть їм одну «Кольорову групу» вручну тут).<br>'
                '3) Після цього на сторінці кожного товару зʼявляться плитки всіх кольорів групи, '
                'а клік по плитці веде на відповідний товар.<br>'
                'Щоб додати ще один колір згодом — створіть товар, виділіть його разом з будь-яким '
                'товаром із групи та знову застосуйте ту саму дію.'
            ),
        }),
        ('AR / 3D', {
            'fields': (
                'ar_texture_preview',
                'ar_texture',
                'ar_status',
                'ar_error',
                'ar_updated_at',
            ),
            'description': (
                'Текстура для 3D/AR генерується з <b>каталожного зображення</b> '
                '(білий фон, вигляд зверху) через Bria product-cutout. '
                'Можна також завантажити PNG з alpha вручну. '
                '<br><button type="button" class="button" id="ar-generate-texture-btn" '
                'style="margin-top:8px;">Згенерувати AR-текстуру з каталожного фото</button>'
                '<span id="ar-generate-texture-status" style="margin-left:10px;"></span>'
            ),
        }),
        ('Інше', {
            'fields': ('has_discount',)
        }),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Для «Активного кольору» вмикаємо віджет з прев'ю кольору/текстури в опціях."""
        if db_field.name == 'active_color':
            kwargs['widget'] = ColorSelectWidget
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
            path(
                'color-swatch-data/',
                self.admin_site.admin_view(self.color_swatch_data),
                name='catalog_product_color_swatch_data'
            ),
            path(
                'scene-size/',
                self.admin_site.admin_view(self.scene_size_lookup),
                name='catalog_product_scene_size'
            ),
            path(
                'generate-images/',
                self.admin_site.admin_view(self.generate_product_images),
                name='catalog_product_generate_images'
            ),
            path(
                'generate-ar-texture/',
                self.admin_site.admin_view(self.generate_ar_texture),
                name='catalog_product_generate_ar_texture'
            ),
            path(
                'generate-seo/',
                self.admin_site.admin_view(self.generate_product_seo),
                name='catalog_product_generate_seo'
            ),
        ]
        return custom_urls + urls

    def scene_size_lookup(self, request):
        """JSON: перший розмір товару для UI-гейту генерації інтер'єру."""
        from catalog.services.scene_size import (
            SceneSizeError,
            get_first_product_size_label,
            resolve_scene_size,
        )

        product_id = (request.GET.get('product_id') or '').strip()
        debug = (request.GET.get('debug') or '') in ('1', 'true', 'yes')

        payload = {
            'success': False,
            'product_id': product_id or None,
            'size_label': None,
            'width_m': None,
            'length_m': None,
            'source': None,
            'error': None,
        }

        if not product_id:
            payload['error'] = 'Потрібен product_id'
            return JsonResponse(payload, status=400)

        try:
            pid = int(product_id)
        except (TypeError, ValueError):
            payload['error'] = 'Невірний product_id'
            return JsonResponse(payload, status=400)

        try:
            product = Product.admin_objects.get(pk=pid)
        except Product.DoesNotExist:
            payload['error'] = f'Товар #{pid} не знайдено'
            return JsonResponse(payload, status=404)

        attrs = list(
            product.product_attr.select_related('size').order_by('pk')
        )
        if debug:
            payload['debug'] = {
                'product_title': product.title,
                'attr_count': len(attrs),
                'attrs': [
                    {
                        'id': a.pk,
                        'size_id': a.size_id,
                        'size_title': (a.size.title if a.size else None),
                        'custom_attribute': a.custom_attribute,
                        'quantity': a.quantity,
                    }
                    for a in attrs
                ],
                'first_size_label': get_first_product_size_label(product),
            }

        try:
            info = resolve_scene_size(product_id=pid)
        except SceneSizeError as exc:
            payload['error'] = str(exc)
            if debug and 'debug' not in payload:
                payload['debug'] = {'first_size_label': None}
            return JsonResponse(payload, status=200)

        payload.update(
            {
                'success': True,
                'size_label': info.label,
                'width_m': str(info.width_m),
                'length_m': str(info.length_m),
                'source': info.source,
            }
        )
        return JsonResponse(payload)

    @method_decorator(require_POST)
    def generate_product_images(self, request):
        phase = request.POST.get('phase', '').strip()
        if phase not in ('catalog', 'hover', 'scene'):
            return JsonResponse(
                {'success': False, 'error': 'Параметр phase має бути catalog, hover або scene'},
                status=400,
            )

        uploaded = request.FILES.get('source_image')
        if not uploaded:
            return JsonResponse({'success': False, 'error': 'Не вибрано файл'}, status=400)

        error = self._validate_source_image(uploaded)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)

        # Ванний комплект: друге фото (прямокутний килимок під двері)
        uploaded_second = request.FILES.get('source_image_2')
        if uploaded_second:
            error = self._validate_source_image(uploaded_second)
            if error:
                return JsonResponse(
                    {'success': False, 'error': f'Друге фото: {error}'}, status=400
                )

        temp_dir = Path(settings.MEDIA_ROOT) / 'temp' / 'replicate' / str(uuid.uuid4())
        temp_dir.mkdir(parents=True, exist_ok=True)
        source_path = temp_dir / self._safe_filename(uploaded.name)
        second_path = None
        service = None

        try:
            with open(source_path, 'wb') as dest:
                for chunk in uploaded.chunks():
                    dest.write(chunk)

            if uploaded_second:
                second_path = temp_dir / (
                    '2_' + self._safe_filename(uploaded_second.name)
                )
                with open(second_path, 'wb') as dest:
                    for chunk in uploaded_second.chunks():
                        dest.write(chunk)

            service = ReplicateProductImageService()
            gen_options = GenerationOptions.from_request_post(request.POST)

            if phase == 'scene':
                try:
                    size_info = resolve_scene_size(
                        product_id=request.POST.get('product_id'),
                        size_label=request.POST.get('size_label'),
                    )
                except SceneSizeError as exc:
                    return JsonResponse(
                        {'success': False, 'error': str(exc), 'phase': phase},
                        status=400,
                    )
                gen_options.scene = gen_options.scene.with_size(size_info)

            image_bytes, meta = service.generate_phase(
                source_path,
                phase,
                gen_options,
                second_source_path=second_path,
            )

            payload = {
                'success': True,
                'phase': phase,
                'meta': meta,
                'logs': meta.get('logs', []),
            }
            if phase == 'catalog':
                payload['image'] = self._file_payload(image_bytes, 'product')
            elif phase == 'hover':
                payload['hover_image'] = self._file_payload(image_bytes, 'hover')
            else:
                payload['image'] = self._file_payload(image_bytes, 'scene')

            return JsonResponse(payload)
        except ReplicateGenerationError as exc:
            logs = service.job_log.entries if service else []
            return JsonResponse(
                {'success': False, 'error': str(exc), 'phase': phase, 'logs': logs},
                status=502,
            )
        except Exception as exc:
            return JsonResponse(
                {'success': False, 'error': f'Помилка генерації: {exc}', 'phase': phase},
                status=500,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _validate_source_image(self, uploaded: UploadedFile) -> str | None:
        allowed = {'image/jpeg', 'image/png', 'image/webp'}
        if uploaded.content_type not in allowed:
            return 'Дозволені лише JPEG, PNG або WebP'

        max_size = 15 * 1024 * 1024
        if uploaded.size > max_size:
            return 'Максимальний розмір файлу — 15 МБ'

        return None

    def _safe_filename(self, name: str) -> str:
        base = os.path.basename(name or 'source.jpg')
        return base.replace('..', '').replace('/', '').replace('\\', '') or 'source.jpg'

    def _file_payload(self, data: bytes, prefix: str) -> dict:
        return {
            'filename': f'{prefix}-{int(time.time())}.webp',
            'content_type': 'image/webp',
            'data_base64': base64.b64encode(data).decode('ascii'),
        }

    def color_swatch_data(self, request):
        """JSON: {id: {color, texture}} — щоб JS міг домалювати кружечок щойно
        створеного кольору в select без перезавантаження сторінки."""
        data = {}
        for c in ProductColor.objects.all():
            data[str(c.pk)] = {
                'color': str(c.color) if c.color else '',
                'texture': c.texture.url if c.texture else '',
            }
        return JsonResponse({'colors': data})

    @admin.action(description='Обʼєднати вибрані в кольорову групу')
    def group_color_variants_action(self, request, queryset):
        """
        Обʼєднує вибрані товари в одну кольорову групу (кольорові варіанти одного килима).
        Якщо хтось із вибраних уже має групу — використовуємо її повторно, інакше створюємо нову.
        Після цього на сторінці кожного товару показуються плитки всіх кольорів групи.
        """
        products = list(queryset)
        if len(products) < 2:
            self.message_user(
                request,
                "Виберіть щонайменше 2 товари, щоб обʼєднати їх у кольорову групу.",
                level='warning'
            )
            return

        # Беремо наявну групу одного з вибраних або створюємо нову
        existing_group = next((p.color_group for p in products if p.color_group_id), None)
        group = existing_group or ColorGroup.objects.create(
            name=products[0].title
        )

        updated = 0
        for product in products:
            if product.color_group_id != group.id:
                product.color_group = group
                product.save(update_fields=['color_group'])
                updated += 1

        self.message_user(
            request,
            f"Обʼєднано {len(products)} товарів у кольорову групу «{group}» "
            f"(оновлено {updated}).",
            level='success'
        )

    @admin.action(description='Видалити з кольорової групи')
    def ungroup_color_variants_action(self, request, queryset):
        """
        Прибирає вибрані товари з їхньої кольорової групи (color_group = None).
        Групи, що стали порожніми, видаляються (перевірка по admin_objects — усі товари,
        навіть без варіацій, щоб не видалити групу, де ще лишились товари).
        """
        grouped = queryset.exclude(color_group__isnull=True)
        affected_group_ids = set(grouped.values_list('color_group_id', flat=True))
        removed = grouped.update(color_group=None)

        deleted_groups = 0
        for gid in affected_group_ids:
            if not Product.admin_objects.filter(color_group_id=gid).exists():
                ColorGroup.objects.filter(id=gid).delete()
                deleted_groups += 1

        if removed == 0:
            self.message_user(
                request,
                "Вибрані товари не належать до жодної кольорової групи.",
                level='warning'
            )
        else:
            self.message_user(
                request,
                f"Прибрано з групи: {removed} товарів. Видалено порожніх груп: {deleted_groups}.",
                level='success'
            )

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
                hover_image=original_product.hover_image,
                is_new=original_product.is_new,
                has_discount=original_product.has_discount,
                active_color=original_product.active_color,
                color_group=original_product.color_group,
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
            for original_image in original_product.images.all().order_by("sort_order", "id"):
                ProductImage.objects.create(
                    product=new_product,
                    image=original_image.image,
                    alt=original_image.alt,
                    sort_order=original_image.sort_order,
                    is_ai=original_image.is_ai,
                )

            # Копіюємо ProductAttribute (порядок уже відсортований Meta.ordering)
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
                    custom_price=original_attr.custom_price,
                    sort_order=original_attr.sort_order,
                )
                # Копіюємо ManyToMany width
                new_attr.width.set(original_widths)
            reorder_product_attributes(new_product)

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

    @method_decorator(require_POST)
    def generate_ar_texture(self, request):
        product_id = request.POST.get('product_id') or request.POST.get('object_id')
        if not product_id:
            return JsonResponse({'success': False, 'error': 'Не вказано product_id'}, status=400)
        try:
            product = Product.admin_objects.get(pk=int(product_id))
        except (Product.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Товар не знайдено'}, status=404)

        if not product.image:
            return JsonResponse(
                {'success': False, 'error': 'Немає каталожного зображення'},
                status=400,
            )

        service = None
        try:
            service = ArTextureService()
            result = service.generate_for_product(product)
            return JsonResponse(result)
        except ReplicateGenerationError as exc:
            logs = service.job_log.entries if service else []
            return JsonResponse(
                {'success': False, 'error': str(exc), 'logs': logs},
                status=502,
            )
        except Exception as exc:
            return JsonResponse(
                {'success': False, 'error': f'Помилка AR: {exc}'},
                status=500,
            )

    @method_decorator(require_POST)
    def generate_product_seo(self, request):
        from catalog.services.seo_generate import ReplicateSeoService, SeoGenerationError

        product_id = request.POST.get('product_id') or request.POST.get('object_id')
        if not product_id:
            return JsonResponse({'success': False, 'error': 'Не вказано product_id'}, status=400)
        try:
            product = Product.admin_objects.get(pk=int(product_id))
        except (Product.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Товар не знайдено'}, status=404)

        if not product.image:
            return JsonResponse(
                {'success': False, 'error': 'Немає каталожного зображення'},
                status=400,
            )

        try:
            result = ReplicateSeoService().generate_for_product(product)
            return JsonResponse(
                {
                    'success': True,
                    'meta_title': result.meta_title,
                    'meta_description': result.meta_description,
                    'meta_keys': result.meta_keys,
                    'description': result.description,
                    'fill_description': result.fill_description,
                    'model': result.model,
                    'duration_sec': result.duration_sec,
                }
            )
        except SeoGenerationError as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=502)
        except Exception as exc:
            return JsonResponse(
                {'success': False, 'error': f'Помилка SEO-генерації: {exc}'},
                status=500,
            )

    @admin.action(description='Згенерувати SEO-описи для вибраних')
    def generate_seo_action(self, request, queryset):
        """
        Ставить у чергу ОДИН Celery-батч (цикл по 1 товару).
        Якщо broker недоступний — синхронний цикл у цьому запиті.
        """
        from catalog.services.seo_generate import generate_seo_for_products

        product_ids = []
        skipped_no_image = 0
        for product in queryset:
            if not product.image:
                skipped_no_image += 1
                continue
            product_ids.append(product.pk)

        if not product_ids:
            self.message_user(
                request,
                'Немає товарів з каталожним фото для SEO-генерації.',
                level='warning',
            )
            return

        try:
            generate_seo_batch_task.delay(product_ids)
            msg = (
                f'SEO-генерацію поставлено в чергу для {len(product_ids)} товар(ів) '
                f'(послідовно, по 1 запиту до Replicate).'
            )
            if skipped_no_image:
                msg += f' Без фото пропущено: {skipped_no_image}.'
            self.message_user(request, msg, level='success')
            return
        except Exception:
            pass

        # Celery broker may be unavailable — sequential sync fallback
        summary = generate_seo_for_products(product_ids)
        parts = [
            f'готово: {summary["ok_count"]}',
            f'помилки: {summary["failed_count"]}',
            f'пропущено: {summary["skipped_count"] + skipped_no_image}',
        ]
        level = 'success' if summary['ok_count'] else 'warning'
        self.message_user(
            request,
            'SEO синхронно (Celery недоступний): ' + ', '.join(parts) + '.',
            level=level,
        )

    @admin.action(description='Опублікувати в соцмережі (TG + Viber + IG + FB)')
    def publish_to_all_socials(self, request, queryset):
        from social.models import SocialPost
        from social.services.product_post import build_product_social_post
        from social.services.publish import (
            enqueue_publish,
            validate_post_for_publish,
        )
        from social.services.telegram_products import post_product_to_channel
        from social.services.viber_products import (
            post_product_to_viber,
            viber_posting_enabled,
        )

        tg_ok = tg_fail = vb_ok = vb_fail = meta_ok = meta_fail = 0
        viber_on = viber_posting_enabled()
        for product in queryset:
            # Telegram products channel
            result = post_product_to_channel(product, force=True)
            if result.get('ok'):
                tg_ok += 1
            else:
                tg_fail += 1
                self.message_user(
                    request,
                    f'{product} → TG: {result.get("error")}',
                    level='error',
                )

            # Viber channel — тільки якщо увімкнений майстер-рубильник
            if viber_on:
                vb_result = post_product_to_viber(product)
                if vb_result.get('ok'):
                    vb_ok += 1
                else:
                    vb_fail += 1
                    self.message_user(
                        request,
                        f'{product} → Viber: {vb_result.get("error")}',
                        level='error',
                    )

            # Instagram + Facebook
            try:
                post = build_product_social_post(product)
            except Exception as exc:
                meta_fail += 1
                self.message_user(request, f'{product} → IG/FB: {exc}', level='error')
                continue
            err = validate_post_for_publish(post)
            if err:
                meta_fail += 1
                post.status = SocialPost.Status.FAILED
                post.last_error = err
                post.save(update_fields=['status', 'last_error', 'updated'])
                self.message_user(request, f'{product} → IG/FB: {err}', level='error')
                continue
            post.status = SocialPost.Status.QUEUED
            post.save(update_fields=['status', 'updated'])
            enqueue_publish(post.pk)
            meta_ok += 1

        viber_part = (
            f'Viber: ok={vb_ok}, fail={vb_fail}'
            if viber_on
            else 'Viber: вимкнено (Social settings)'
        )
        self.message_user(
            request,
            f'TG: ok={tg_ok}, fail={tg_fail} · {viber_part} · '
            f'IG/FB: у черзі {meta_ok}, помилок {meta_fail}. '
            f'Статус IG/FB — у Social → Social posts.',
            level='success' if (tg_ok or vb_ok or meta_ok) else 'warning',
        )

    @admin.action(description='Згенерувати AR-текстуру для вибраних')
    def generate_ar_texture_action(self, request, queryset):
        queued = 0
        synced = 0
        skipped = 0
        for product in queryset:
            if not product.image:
                skipped += 1
                continue
            product.ar_status = Product.AR_STATUS_PENDING
            product.ar_error = ''
            product.save(update_fields=['ar_status', 'ar_error'])
            try:
                generate_ar_texture_task.delay(product.pk)
                queued += 1
            except Exception:
                # Celery broker may be unavailable — run sync
                try:
                    ArTextureService().generate_for_product(product)
                    synced += 1
                except Exception as exc:
                    product.ar_status = Product.AR_STATUS_FAILED
                    product.ar_error = str(exc)[:2000]
                    product.save(update_fields=['ar_status', 'ar_error'])
                    skipped += 1

        parts = []
        if queued:
            parts.append(f'у чергу Celery: {queued}')
        if synced:
            parts.append(f'синхронно: {synced}')
        if skipped:
            parts.append(f'пропущено/помилка: {skipped}')
        self.message_user(
            request,
            'AR-текстура: ' + (', '.join(parts) if parts else 'нічого не зроблено'),
            level='success' if (queued or synced) else 'warning',
        )

    def ar_texture_preview(self, obj):
        if obj.ar_texture:
            return format_html(
                '<div style="display:inline-block;padding:8px;'
                'background:repeating-conic-gradient(#ccc 0% 25%,#fff 0% 50%) 50%/16px 16px;">'
                '<img src="{}" style="max-width:220px;max-height:220px;display:block;" />'
                '</div>',
                obj.ar_texture.url,
            )
        return format_html('<span style="color:#999;">— немає текстури</span>')

    ar_texture_preview.short_description = 'Превʼю AR-текстури'

    def get_ar_status_display_col(self, obj):
        colors = {
            Product.AR_STATUS_READY: '#28a745',
            Product.AR_STATUS_PENDING: '#f0ad4e',
            Product.AR_STATUS_FAILED: '#dc3545',
            Product.AR_STATUS_NONE: '#999',
        }
        color = colors.get(obj.ar_status, '#999')
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            color,
            obj.get_ar_status_display(),
        )

    get_ar_status_display_col.short_description = 'AR'
    get_ar_status_display_col.admin_order_field = 'ar_status'

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None:
            return fieldsets
        # Форма створення: галочка автопосту (у ProductAdminForm вона є лише
        # тут, тож у fieldsets її треба додати теж динамічно)
        return tuple(fieldsets) + (
            ('Соцмережі', {
                'fields': ('post_to_socials',),
                'description': (
                    'Новий товар автоматично піде в Telegram, Instagram/Facebook '
                    'і Viber (ті, що увімкнені в Social settings). '
                    'Зніміть галочку, щоб додати товар тихо.'
                ),
            }),
        )

    def save_model(self, request, obj, form, change):
        prev_texture = None
        if change and obj.pk:
            prev = Product.admin_objects.filter(pk=obj.pk).only('ar_texture').first()
            if prev and prev.ar_texture:
                prev_texture = prev.ar_texture.name
        # Рішення менеджера читає signals.py. Виставляємо ДО save(), бо
        # post_save спрацьовує всередині super().save_model().
        # При редагуванні поля у формі немає — і сигнал усе одно мовчить
        # (created=False), тож повторного посту бути не може.
        if not change:
            obj._social_autopost_choice = bool(
                form.cleaned_data.get('post_to_socials', True)
            )
        super().save_model(request, obj, form, change)
        new_name = obj.ar_texture.name if obj.ar_texture else None
        if new_name and new_name != prev_texture:
            mark_ar_ready_from_manual_upload(obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if form.instance.pk:
            reorder_product_attributes(form.instance)

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

    def get_color_group_display(self, obj):
        """Показує кольорову групу товару (ID + кількість варіантів). Однаковий #ID = одна група.
        Колір бейджа детермінований від ID групи (золотий кут) — різні групи легко розрізнити."""
        if obj.color_group_id:
            count = obj.color_group.variants.count()
            hue = (obj.color_group_id * 137) % 360  # золотий кут → рівномірний розкид кольорів
            bg = "hsl({}, 60%, 40%)".format(hue)
            return format_html(
                '<span style="display:inline-block; padding:2px 8px; border-radius:10px; '
                'background:{}; color:#fff; font-weight:600; white-space:nowrap;" '
                'title="{}">#{} · {} шт.</span>',
                bg,
                obj.color_group.name or '',
                obj.color_group_id,
                count,
            )
        return format_html('<span style="color: var(--body-quiet-color, #999);">—</span>')

    get_color_group_display.short_description = 'Кольор. група'
    get_color_group_display.admin_order_field = 'color_group'

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
        # Порядок як у Django autocomplete: jquery → select2 → jquery.init,
        # щоб select2 коректно прикріпився до django.jQuery.
        js = (
            'admin/js/vendor/jquery/jquery.js',
            'admin/js/vendor/select2/select2.full.js',
            'admin/js/jquery.init.js',
            'admin/js/product_specification_inline.js',
            'admin/js/color_select.js',
            'admin/js/image_resize.js',
            'admin/js/replicate_generate_images.js',
            'admin/js/replicate_generate_scene.js',
            'admin/js/replicate_generate_seo.js',
            'admin/js/ar_generate_texture.js',
            'admin/js/product_image_sortable.js',
            'admin/js/product_image_dropzone.js',
            'admin/js/product_form_validate.js',
        )
        css = {
            'all': (
                'admin/css/product_admin.css',
                'admin/css/vendor/select2/select2.css',
                'admin/css/autocomplete.css',  # тема select2 під адмінку (світла/темна)
                'admin/css/color_select.css',
            )
        }

    class Meta:
        model = Product


admin.site.register(Product, ProductAdmin)
