from functools import reduce
from operator import or_

from django import db
from django.db.models import Min, ExpressionWrapper, F, fields, Subquery, Q, Case, When, Value
from django_filters import rest_framework as rest_filters

from ..models import Product, Specification, SpecificationValue, ProductSpecification


class ProductFilter(rest_filters.FilterSet):
    size = rest_filters.CharFilter(field_name="product_attr__size")
    price = rest_filters.OrderingFilter(
        fields=("product_attr__price",), method="order_by_price"
    )
    title = rest_filters.OrderingFilter(fields=("title",))
    color = rest_filters.CharFilter(
        field_name="product_specs__spec_value__title", method="filter_by_color"
    )
    search_query = rest_filters.CharFilter(method="search", label="Search query")

    class Meta:
        model = Product
        fields = ["size", "price", "search_query"]

    def order_by_price(self, queryset, name, value):
        min_price_attr_subquery = queryset.annotate(
            product_attr__price=Min(
                ExpressionWrapper(
                    F("product_attr__price")
                    - F("product_attr__price") * F("product_attr__discount") / 100
                    if F("product_attr__discount") is not None
                    else F("product_attr__price"),
                    output_field=fields.FloatField(),
                )
            )
        ).order_by(value[0])
        return min_price_attr_subquery

    def filter_by_color(self, queryset, name, value):
        specs = ProductSpecification.objects.filter(
            specification__title="Колір", spec_value__title=value
        )
        return queryset.filter(product_specs__in=specs)

    # def search(self, queryset, name, value):
    #     exact_search = queryset.filter(
    #         Q(title__icontains=value) | Q(description__icontains=value)
    #     )
    #     if not exact_search:
    #         values = value.split(" ")
    #         for val in values:
    #             partial_search = queryset.filter(
    #                 Q(title__icontains=val) | Q(description__icontains=val)
    #             )
    #             if partial_search:
    #                 return partial_search
    #     return exact_search

    def search(self, queryset, name, value):
        """
        Пошук товарів з пріоритетом точного збігу title
        Спочатку шукаємо точний збіг (title__iexact), потім частковий (title__icontains)
        """
        # Спочатку шукаємо точний збіг title (вищий пріоритет)
        exact_match = queryset.filter(title__iexact=value)
        
        if exact_match.exists():
            # Якщо знайдено точний збіг, повертаємо тільки його
            return exact_match.annotate(
                custom_order=Case(
                    When(title__iexact=value, then=Value(1)),
                    output_field=db.models.IntegerField(),
                )
            ).order_by("custom_order", "-created")
        
        # Якщо точного збігу немає, шукаємо частковий
        result = (
            queryset.annotate(
                custom_order=Case(
                    When(title__icontains=value, then=Value(1)),
                    When(description__icontains=value, then=Value(2)),
                    output_field=db.models.IntegerField(),
                )
            )
            .filter(custom_order__gt=0)
            .order_by("custom_order", "-created")
        )
        return result
