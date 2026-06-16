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


def get_available_filters(products_queryset, data=None):
    """
    Отримує доступні фільтри (фасети).

    Якщо передано `data` (request.GET) — застосовується фасетна логіка: для кожного
    фасета його значення рахуються з `products_queryset` (база), відфільтрованої УСІМА
    активними фільтрами, КРІМ власного фасета. Завдяки цьому вибір одного виробника НЕ
    ховає інших виробників (можна обрати кілька), але інші фасети звужуються під вибір.

    Без `data` — рахує напряму з переданого queryset (стара поведінка, сумісність).
    """
    from .filters import ProductFilter
    from catalog.models import ProductAttribute

    base = products_queryset

    def facet_ids(*exclude_keys):
        """
        Список ID товарів бази, відфільтрованої всіма активними фільтрами, КРІМ exclude_keys.
        Матеріалізуємо в чистий список ID (без анотацій/сортування ProductManager), щоб
        уникнути крихких вкладених підзапитів. Ключі виключаємо регістро-/пробіло-незалежно.
        """
        if not data:
            qs = base
        else:
            excl = {k.lower().strip() for k in exclude_keys}
            sub = data.copy()
            for key in list(sub.keys()):
                if key.lower().strip() in excl:
                    del sub[key]
            qs = ProductFilter(sub, base).qs
        return list(qs.order_by().values_list('id', flat=True).distinct())

    filters = {}

    # Розміри (виключаємо власний фасет 'size')
    size_ids = facet_ids('size')
    filters['sizes'] = Size.objects.filter(
        product_attr__product_id__in=size_ids
    ).distinct().annotate(
        count=Count('product_attr__product', distinct=True)
    ).order_by('title')

    # Кольори (виключаємо власний фасет 'color')
    color_ids = facet_ids('color')
    filters['colors'] = ProductColor.objects.filter(
        product_id__in=color_ids
    ).distinct().annotate(
        count=Count('product', distinct=True)
    ).order_by('title')

    # Специфікації (для кожної виключаємо її власний ключ = title у нижньому регістрі)
    specifications = Specification.objects.all()
    available_specs = {}

    for spec in specifications:
        spec_ids = facet_ids(spec.title.lower())
        spec_values = SpecificationValue.objects.filter(
            product_specs__product_id__in=spec_ids,
            product_specs__specification=spec
        ).distinct().annotate(
            count=Count('product_specs__product', distinct=True)
        ).order_by('title')

        if spec_values.exists():
            available_specs[spec.title] = spec_values

    filters['specifications'] = available_specs

    # Діапазон цін з урахуванням кастомних товарів та знижок (виключаємо price_min/price_max)
    price_ids = facet_ids('price_min', 'price_max')
    all_prices = []
    for attr in ProductAttribute.objects.filter(product_id__in=price_ids):
        if attr.custom_attribute and attr.custom_price:
            all_prices.append(float(attr.custom_price))
        elif attr.price:
            if attr.discount:
                all_prices.append(float(attr.price) - (float(attr.price) * float(attr.discount) / 100))
            else:
                all_prices.append(float(attr.price))

    # Для максимальної ціни - з усіх товарів на сайті (оригінальна ціна без знижки)
    all_max_prices = []
    for attr in ProductAttribute.objects.all():
        if attr.custom_attribute and attr.custom_price:
            all_max_prices.append(float(attr.custom_price))
        elif attr.price:
            all_max_prices.append(float(attr.price))

    min_price = min(all_prices) if all_prices else None
    max_price = max(all_max_prices) if all_max_prices else (max(all_prices) if all_prices else None)

    filters['price_range'] = {
        'min_price': min_price,
        'max_price': max_price
    }

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