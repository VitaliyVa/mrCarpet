import django_filters
from django.db.models import Min, Q, Case, When, ExpressionWrapper, F, FloatField
from django.db.models.functions import Coalesce

from .models import Product, ProductSpecification, Specification


class ProductFilter(django_filters.FilterSet):
    size = django_filters.CharFilter(field_name="product_attr__size")
    price = django_filters.OrderingFilter(
        fields=("product_attr__price",), method="order_by_price"
    )
    title = django_filters.OrderingFilter(fields=("title",))
    color = django_filters.CharFilter(
        field_name="product_specs__spec_value__title", method="filter_by_color"
    )
    q = django_filters.CharFilter(method="search", label="Search query")

    class Meta:
        model = Product
        fields = ["size", "price"]

    def filter_queryset(self, queryset):
        """
        Перевизначаємо filter_queryset для обробки динамічних фільтрів специфікацій
        """
        # Спочатку застосовуємо стандартні фільтри
        queryset = super().filter_queryset(queryset)
        
        # Фільтрація по діапазону цін (price_min, price_max)
        price_min = self.data.get('price_min')
        price_max = self.data.get('price_max')
        
        if price_min or price_max:
            # Анотуємо effective_price_attr для кожної варіації: кастомна -> custom_price, інша -> ціна з урахуванням знижки (або без)
            effective_price_expr = Case(
                When(
                    product_attr__custom_attribute=True,
                    then=F('product_attr__custom_price')
                ),
                default=ExpressionWrapper(
                    F('product_attr__price') * (1 - Coalesce(F('product_attr__discount'), 0) / 100.0),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )

            queryset = queryset.annotate(
                effective_price_attr=effective_price_expr
            ).annotate(
                effective_price=Min('effective_price_attr')
            )
            
            if price_min:
                try:
                    price_min_value = float(price_min)
                    queryset = queryset.filter(effective_price__gte=price_min_value)
                except (ValueError, TypeError):
                    pass
            
            if price_max:
                try:
                    price_max_value = float(price_max)
                    queryset = queryset.filter(effective_price__lte=price_max_value)
                except (ValueError, TypeError):
                    pass
        
        # Обробляємо динамічні фільтри для специфікацій
        # Отримуємо всі назви специфікацій
        all_specs = Specification.objects.values_list('title', flat=True)
        
        # Перевіряємо всі GET параметри
        for key, value in self.data.items():
            # Пропускаємо price_min/price_max (вже оброблено вище)
            if key in ['price_min', 'price_max']:
                continue
                
            # Перевіряємо чи це специфікація (назва в нижньому регістрі)
            spec_name_lower = key.lower()
            spec_name_matches = [spec for spec in all_specs if spec.lower() == spec_name_lower]
            
            if spec_name_matches and value:
                # Знайшли специфікацію, фільтруємо по ній
                spec_name = spec_name_matches[0]
                specs = ProductSpecification.objects.filter(
                    specification__title=spec_name,
                    spec_value__title=value
                )
                queryset = queryset.filter(product_specs__in=specs).distinct()
        
        return queryset

    def order_by_price(self, queryset, name, value):
        effective_price_expr = Case(
            When(
                product_attr__custom_attribute=True,
                then=F('product_attr__custom_price')
            ),
            default=ExpressionWrapper(
                F('product_attr__price') * (1 - Coalesce(F('product_attr__discount'), 0) / 100.0),
                output_field=FloatField()
            ),
            output_field=FloatField()
        )

        queryset = queryset.annotate(
            effective_price_attr=effective_price_expr
        ).annotate(min_effective_price=Min('effective_price_attr'))

        sort_value = value[0] if value else 'min_effective_price'
        if sort_value.startswith('-'):
            return queryset.order_by('-min_effective_price').distinct()
        return queryset.order_by('min_effective_price').distinct()

    def filter_by_color(self, queryset, name, value):
        specs = ProductSpecification.objects.filter(
            specification__title="Колір", spec_value__title=value
        )
        return queryset.filter(product_specs__in=specs)

    def search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )
