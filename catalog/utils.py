from .models import Favourite
from django.db.models import Count, Min, Max, Case, When, DecimalField, Q, ExpressionWrapper, F
from .models import Specification, SpecificationValue, Size, ProductColor


def get_favourite(request) -> Favourite:
    if request.user.is_authenticated:
        try:
            favourite = Favourite.objects.get(user=request.user)
        except:
            favourite = Favourite.objects.create(user=request.user)
    else:
        try:
            fav_id = request.session.get("fav_id")
            favourite = Favourite.objects.get(id=fav_id)
        except:
            favourite = Favourite.objects.create()
            request.session["fav_id"] = favourite.id
    return favourite


def get_available_filters(products_queryset):
    """
    Отримує актуальні фільтри на основі поточного набору товарів
    """
    filters = {}
    
    # Отримуємо доступні розміри
    available_sizes = Size.objects.filter(
        product_attr__product__in=products_queryset
    ).distinct().annotate(
        count=Count('product_attr__product', distinct=True)
    ).order_by('title')
    
    filters['sizes'] = available_sizes
    
    # Отримуємо доступні кольори
    available_colors = ProductColor.objects.filter(
        product__in=products_queryset
    ).distinct().annotate(
        count=Count('product', distinct=True)
    ).order_by('title')
    
    filters['colors'] = available_colors
    
    # Отримуємо доступні специфікації
    specifications = Specification.objects.all()
    available_specs = {}
    
    for spec in specifications:
        spec_values = SpecificationValue.objects.filter(
            product_specs__product__in=products_queryset,
            product_specs__specification=spec
        ).distinct().annotate(
            count=Count('product_specs__product', distinct=True)
        ).order_by('title')
        
        if spec_values.exists():
            available_specs[spec.title] = spec_values
    
    filters['specifications'] = available_specs
    
    # Отримуємо діапазон цін з урахуванням кастомних товарів та знижок
    # Для кастомних товарів використовуємо custom_price, для звичайних - price зі знижкою якщо є
    from catalog.models import ProductAttribute
    from django.db.models import FloatField
    
    # Збираємо всі ціни з обох полів з урахуванням знижок
    all_prices = []
    
    # Для мінімальної ціни - з поточного queryset
    product_attrs = ProductAttribute.objects.filter(product__in=products_queryset)
    for attr in product_attrs:
        if attr.custom_attribute and attr.custom_price:
            all_prices.append(float(attr.custom_price))
        elif attr.price:
            # Обчислюємо ціну зі знижкою якщо є
            if attr.discount:
                price_with_discount = float(attr.price) - (float(attr.price) * float(attr.discount) / 100)
                all_prices.append(price_with_discount)
            else:
                all_prices.append(float(attr.price))
    
    # Для максимальної ціни - з усіх товарів на сайті
    all_product_attrs = ProductAttribute.objects.all()
    all_max_prices = []
    for attr in all_product_attrs:
        if attr.custom_attribute and attr.custom_price:
            all_max_prices.append(float(attr.custom_price))
        elif attr.price:
            # Без знижки для максимальної (беремо оригінальну ціну)
            all_max_prices.append(float(attr.price))
    
    min_price = min(all_prices) if all_prices else None
    max_price = max(all_max_prices) if all_max_prices else (max(all_prices) if all_prices else None)
    
    price_range = {
        'min_price': min_price,
        'max_price': max_price
    }
    
    filters['price_range'] = price_range
    
    return filters


def get_filter_counts(products_queryset, current_filters=None):
    """
    Отримує кількість товарів для кожного значення фільтра
    """
    if current_filters is None:
        current_filters = {}
    
    counts = {}
    
    # Розміри
    size_counts = Size.objects.filter(
        product_attr__product__in=products_queryset
    ).distinct().annotate(
        count=Count('product_attr__product', distinct=True)
    ).values('id', 'title', 'count')
    
    counts['sizes'] = {item['id']: {'title': item['title'], 'count': item['count']} for item in size_counts}
    
    # Кольори
    color_counts = ProductColor.objects.filter(
        product__in=products_queryset
    ).distinct().annotate(
        count=Count('product', distinct=True)
    ).values('id', 'title', 'count')
    
    counts['colors'] = {item['id']: {'title': item['title'], 'count': item['count']} for item in color_counts}
    
    # Специфікації
    specifications = Specification.objects.all()
    spec_counts = {}
    
    for spec in specifications:
        spec_value_counts = SpecificationValue.objects.filter(
            product_specs__product__in=products_queryset,
            product_specs__specification=spec
        ).distinct().annotate(
            count=Count('product_specs__product', distinct=True)
        ).values('id', 'title', 'count')
        
        spec_counts[spec.title] = {item['id']: {'title': item['title'], 'count': item['count']} for item in spec_value_counts}
    
    counts['specifications'] = spec_counts
    
    return counts