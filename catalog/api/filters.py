from functools import reduce
from operator import or_

from django.db.models import Min, ExpressionWrapper, F, fields, Subquery, Q
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
        fields = ["size", "price"]

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
        search_terms = value.split(" ")
        exact_search_q = Q(title__icontains=value) | Q(description__icontains=value)
        partial_search_q_list = [
            Q(title__icontains=val) | Q(description__icontains=val)
            for val in search_terms
        ]
        partial_search_q = reduce(or_, partial_search_q_list)
        result_queryset = queryset.filter(exact_search_q | partial_search_q)
        return result_queryset
