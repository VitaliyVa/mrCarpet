import django_filters
from django.db.models import Min, Q

from .models import Product, ProductSpecification


class ProductFilter(django_filters.FilterSet):
    size = django_filters.CharFilter(field_name="product_attr__size", method='filter_by_size')
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

    def filter_by_size(self, queryset, name, value):
        int_check = lambda a: a.isdigit()
        value_list = value.split(',')

        if not all(map(int_check, value_list)):
            return queryset

        lookup = {f'{name}__in': value_list}

        return queryset.filter(**lookup)
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
