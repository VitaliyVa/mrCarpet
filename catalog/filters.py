import django_filters
from django.db.models import Min, Q

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
        
        # Обробляємо динамічні фільтри для специфікацій
        # Отримуємо всі назви специфікацій
        all_specs = Specification.objects.values_list('title', flat=True)
        
        # Перевіряємо всі GET параметри
        for key, value in self.data.items():
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
        return (
            queryset.annotate(product_attr__price=Min("product_attr__price"))
            .order_by(value[0])
            .distinct()
        )

    def filter_by_color(self, queryset, name, value):
        specs = ProductSpecification.objects.filter(
            specification__title="Колір", spec_value__title=value
        )
        return queryset.filter(product_specs__in=specs)

    def search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )
