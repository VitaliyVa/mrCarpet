from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Min, Q, Case, When, Value, IntegerField, F, ExpressionWrapper, FloatField
from django.db.models.functions import Coalesce
from django.http import JsonResponse

from .filters import ProductFilter
from .models import (
    Product,
    Favourite,
    FavouriteProducts,
    ProductCategory,
    ProductAttribute,
    Size, ProductImage,
)
from .utils import get_available_filters, get_filter_counts


# Create your views here.
def catalog_detail(request, slug):
    categorie = ProductCategory.objects.get(slug=slug)
    products = categorie.products.all()
    
    # Застосовуємо сортування
    sort_param = request.GET.get('sort')
    if sort_param:
        if sort_param == 'title':
            products = products.order_by('title')
        elif sort_param == '-title':
            products = products.order_by('-title')
        elif sort_param == 'price':
            effective_price_expr = Case(
                When(product_attr__custom_attribute=True, then=F('product_attr__custom_price')),
                default=ExpressionWrapper(
                    F('product_attr__price') * (1 - Coalesce(F('product_attr__discount'), 0) / 100.0),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )
            products = products.annotate(
                effective_price_attr=effective_price_expr
            ).annotate(min_price=Min('effective_price_attr')).order_by('min_price')
        elif sort_param == '-price':
            effective_price_expr = Case(
                When(product_attr__custom_attribute=True, then=F('product_attr__custom_price')),
                default=ExpressionWrapper(
                    F('product_attr__price') * (1 - Coalesce(F('product_attr__discount'), 0) / 100.0),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )
            products = products.annotate(
                effective_price_attr=effective_price_expr
            ).annotate(min_price=Min('effective_price_attr')).order_by('-min_price')
    
    # Застосовуємо фільтри
    filter_set = ProductFilter(request.GET, products)
    products = filter_set.qs
    
    # Отримуємо актуальні фільтри на основі поточних товарів
    available_filters = get_available_filters(products)
    
    # Пагінація
    paginator = Paginator(products, 12)  # 12 товарів на сторінку
    page = request.GET.get('page')
    
    try:
        products = paginator.page(page)
    except PageNotAnInteger:
        products = paginator.page(1)
    except EmptyPage:
        products = paginator.page(paginator.num_pages)
    
    return render(
        request,
        "catalog_inside.html",
        {
            "categorie": categorie, 
            "products": products, 
            "available_filters": available_filters,
            "current_filters": request.GET,
        },
    )


def catalog(request):
    products = Product.objects.all()
    # filter_set = ProductFilter(request.GET, products)
    # products = filter_set.qs
    
    # Пагінація
    paginator = Paginator(products, 12)  # 12 товарів на сторінку
    page = request.GET.get('page')
    
    try:
        products = paginator.page(page)
    except PageNotAnInteger:
        products = paginator.page(1)
    except EmptyPage:
        products = paginator.page(paginator.num_pages)
    
    return render(request, "catalog.html", {"products": products})


def search_products(request):
    """API view для пошуку товарів"""
    search_query = request.GET.get('search_query', '').strip()
    if not search_query or len(search_query) < 2:
        return JsonResponse([], safe=False)
    
    # Базовий queryset
    products = Product.objects.all()
    
    # Створюємо складний Q об'єкт для пошуку
    search_q = Q()
    
    # Пошук за назвою товару (найвищий пріоритет)
    search_q |= Q(title__icontains=search_query)
    search_q |= Q(title__icontains=search_query.lower())
    search_q |= Q(title__icontains=search_query.upper())
    search_q |= Q(title__icontains=search_query.capitalize())
    
    # Пошук за slug товару
    search_q |= Q(slug__icontains=search_query)
    search_q |= Q(slug__icontains=search_query.lower())
    
    # Пошук за описом товару
    search_q |= Q(description__icontains=search_query)
    search_q |= Q(description__icontains=search_query.lower())
    
    # Пошук за категоріями
    search_q |= Q(categories__title__icontains=search_query)
    
    # Пошук за кольорами
    search_q |= Q(colors__title__icontains=search_query)
    
    # Пошук за характеристиками товару
    search_q |= Q(product_specs__specification__title__icontains=search_query)
    search_q |= Q(product_specs__spec_value__title__icontains=search_query)
    
    # Пошук за розмірами
    search_q |= Q(product_attr__size__title__icontains=search_query)
    
    # Додатковий пошук по окремих словах (завжди виконуємо)
    search_words = search_query.split()
    for word in search_words:
        if len(word) >= 2:  # Шукаємо тільки слова довжиною 2+ символи
            search_q |= Q(title__icontains=word)
            search_q |= Q(title__icontains=word.lower())
            search_q |= Q(title__icontains=word.capitalize())
            search_q |= Q(slug__icontains=word)
            search_q |= Q(slug__icontains=word.lower())
            search_q |= Q(description__icontains=word)
            search_q |= Q(description__icontains=word.lower())
            search_q |= Q(categories__title__icontains=word)
            search_q |= Q(categories__title__icontains=word.lower())
            search_q |= Q(colors__title__icontains=word)
            search_q |= Q(colors__title__icontains=word.lower())
    
    # Додатковий пошук по частинах слів (для довших слів)
    for word in search_words:
        if len(word) >= 4:  # Для слів довжиною 4+ символи шукаємо по частинах
            # Шукаємо по перших 3+ символах слова
            for i in range(3, len(word)):
                partial = word[:i]
                search_q |= Q(title__icontains=partial)
                search_q |= Q(title__icontains=partial.lower())
                search_q |= Q(slug__icontains=partial)
                search_q |= Q(slug__icontains=partial.lower())
    
    # Застосовуємо пошук
    products = products.filter(search_q).distinct()
    
    # Сортуємо результати за релевантністю з пріоритетами
    products = products.annotate(
        search_priority=Case(
            # Найвищий пріоритет - точне співпадіння в назві
            When(title__iexact=search_query, then=Value(10)),
            # Високий пріоритет - назва починається з пошукового запиту
            When(title__istartswith=search_query, then=Value(9)),
            # Високий пріоритет - назва містить пошуковий запит
            When(title__icontains=search_query, then=Value(8)),
            # Високий пріоритет - slug містить пошуковий запит
            When(slug__icontains=search_query, then=Value(7)),
            # Середній пріоритет - опис містить пошуковий запит
            When(description__icontains=search_query, then=Value(6)),
            # Середній пріоритет - категорія містить пошуковий запит
            When(categories__title__icontains=search_query, then=Value(5)),
            # Низький пріоритет - колір містить пошуковий запит
            When(colors__title__icontains=search_query, then=Value(4)),
            # Низький пріоритет - характеристики містять пошуковий запит
            When(product_specs__specification__title__icontains=search_query, then=Value(3)),
            When(product_specs__spec_value__title__icontains=search_query, then=Value(3)),
            # Мінімальний пріоритет - розмір містить пошуковий запит
            When(product_attr__size__title__icontains=search_query, then=Value(2)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )
    
    # Додаємо додаткові пріоритети для окремих слів
    for word in search_words:
        if len(word) >= 2:
            products = products.annotate(
                word_priority=Case(
                    When(title__icontains=word, then=Value(2)),
                    When(title__icontains=word.lower(), then=Value(2)),
                    When(title__icontains=word.capitalize(), then=Value(2)),
                    When(slug__icontains=word, then=Value(2)),
                    When(slug__icontains=word.lower(), then=Value(2)),
                    When(description__icontains=word, then=Value(1)),
                    When(description__icontains=word.lower(), then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
            # Додаємо пріоритет слова до загального пріоритету
            products = products.annotate(
                search_priority=F('search_priority') + F('word_priority')
            )
    
    # Сортуємо за пріоритетом
    products = products.order_by('-search_priority', 'title')
    
    # Обмежуємо до 15 результатів
    products = products[:15]
    
    # Формуємо результат для фронтенду
    results = []
    for product in products:
        # Знаходимо мінімальну ціну для товару
        min_price = product.product_attr.aggregate(
            min_price=Min('price')
        )['min_price']
        
        # Знаходимо знижку
        max_discount = product.product_attr.aggregate(
            max_discount=Min('discount')
        )['max_discount']
        
        # Формуємо зображення
        image_url = product.image.url if product.image else '/static/utils/assets/img.png'
        
        # Формуємо категорії
        categories = [cat.title for cat in product.categories.all()[:2]]
        category_text = ', '.join(categories) if categories else ''
        
        results.append({
            'id': product.id,
            'title': product.title,
            'image': image_url,
            'href': product.get_absolute_url(),
            'price': min_price,
            'discount': max_discount,
            'categories': category_text,
            'is_new': product.is_new,
            'has_discount': product.has_discount
        })
    
    return JsonResponse(results, safe=False)


# @login_required
def favourites(request):
    # favourite = Favourite.objects.get(user=request.user)
    # f_products = favourite.product.all()[::-1]
    # favorites = FavouriteProducts.objects.filter(favourite=favourite)
    return render(request, "favorite.html")


def product(request, slug):
    product = Product.objects.get(slug=slug)
    images = ProductImage.objects.filter(product=product)
    # product_attr = ProductAttribute.objects.filter(product=prod)
    return render(request, "product.html", {"product": product, "images": images})


def stock(request):
    products = Product.objects.filter(has_discount=True)
    
    # Пагінація
    paginator = Paginator(products, 12)  # 12 товарів на сторінку
    page = request.GET.get('page')
    
    try:
        products = paginator.page(page)
    except PageNotAnInteger:
        products = paginator.page(1)
    except EmptyPage:
        products = paginator.page(paginator.num_pages)
    
    return render(request, "catalog.html", {"products": products})