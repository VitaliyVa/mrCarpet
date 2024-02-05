import django_filters
from django.db.models import Min, Q

from .models import Product, ProductSpecification


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
