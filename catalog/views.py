from django.shortcuts import get_object_or_404
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
from .utils import (
    auto_related_products,
    get_available_filters,
    get_filter_counts,
    primary_category,
)


def _analytics_view_item_payload(product: Product, attr=None) -> dict | None:
    """GA4/GTM ecommerce view_item payload (None when price unknown)."""
    from decimal import Decimal

    from project.merchant_feed import offer_id

    if attr is None:
        attr = product.product_attr.order_by("sort_order", "pk").first()
    if not attr:
        return None
    if attr.custom_attribute:
        price = attr.custom_price
    else:
        price = attr.get_total_price()
    if price is None:
        return None
    if isinstance(price, Decimal):
        price = float(price)
    category = product.categories.first()
    room = primary_category(product)
    # Same item shape as cart lines (project/ga4_ecommerce.py) so GA4 joins
    # view_item → add_to_cart → purchase on item_id + item_variant.
    variant = ""
    if not attr.custom_attribute and getattr(attr, "size", None):
        variant = str(attr.size)
    return {
        # Merchant feed g:id of this size (bare pk for cut-to-length).
        "item_id": offer_id(product, attr),
        "item_group_id": str(product.pk),
        "item_name": product.title,
        "item_brand": "mr.Carpet",
        "item_category": category.title if category else "",
        # item_category stays as before (cart lines and old GA4 reports use
        # it); the room/purpose category goes to the next level when it differs.
        **(
            {"item_category2": room.title}
            if room is not None and category is not None and room.pk != category.pk
            else {}
        ),
        "item_variant": variant,
        "price": round(float(price), 2),
        "quantity": 1,
        "currency": "UAH",
    }


# Create your views here.
def catalog_detail(request, slug):
    from django.urls import reverse

    from project.seo_content import get_seo_guides
    from project.seo_jsonld import breadcrumb_graph, dumps_jsonld

    categorie = get_object_or_404(ProductCategory, slug=slug)
    base_products = categorie.products.all()
    products = base_products
    
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
    
    # Доступні фільтри (фасети) — з базового набору категорії, щоб вибір одного
    # значення фасета не ховав інші його значення
    available_filters = get_available_filters(base_products, request.GET)
    
    # Пагінація
    paginator = Paginator(products, 12)  # 12 товарів на сторінку
    page = request.GET.get('page')
    
    try:
        products = paginator.page(page)
    except PageNotAnInteger:
        products = paginator.page(1)
    except EmptyPage:
        products = paginator.page(paginator.num_pages)
    
    from project.seo_jsonld import breadcrumb_graph, dumps_jsonld

    crumbs = [
        ("Головна", "/"),
        ("Каталог", reverse("catalog")),
        (categorie.title, categorie.get_absolute_url()),
    ]
    return render(
        request,
        "catalog_inside.html",
        {
            "categorie": categorie,
            "products": products,
            "available_filters": available_filters,
            "current_filters": request.GET,
            "breadcrumb_jsonld": dumps_jsonld(breadcrumb_graph(request, crumbs)),
            "seo_guides": get_seo_guides(categorie),
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


def _apply_product_sort(products, sort_param):
    """Сортування товарів за параметром sort (title / -title / price / -price)."""
    if not sort_param:
        return products
    if sort_param == 'title':
        return products.order_by('title')
    if sort_param == '-title':
        return products.order_by('-title')
    if sort_param in ('price', '-price'):
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
        ).annotate(min_price=Min('effective_price_attr'))
        return products.order_by('min_price' if sort_param == 'price' else '-min_price')
    return products


#: <title> of /catalog/collection/. "Вся колекція" said nothing a buyer types;
#: the H1 and breadcrumbs keep the short menu label.
COLLECTION_META_TITLE = "Купити килим: усі моделі з цінами і розмірами"
COLLECTION_FALLBACK_DESCRIPTION = "Вся колекція килимів mr.Carpet. Доставка по Україні."


def _collection_meta_description(base_products) -> str:
    """
    Description for /catalog/collection/ built from the live catalogue:
    how many models and the lowest in-stock fixed-size price. Nothing is
    hardcoded, so it stays true as the range changes.
    """
    from catalog.templatetags.catalog_filters import plural_uk_form

    count = base_products.count()
    if not count:
        return COLLECTION_FALLBACK_DESCRIPTION
    low = (
        ProductAttribute.objects.filter(
            product__in=base_products.values("pk"),
            custom_attribute=False,
            price__gt=0,
            quantity__gt=0,
        )
        .annotate(
            final_price=ExpressionWrapper(
                F("price") * (1 - Coalesce(F("discount"), 0) / 100.0),
                output_field=FloatField(),
            )
        )
        .aggregate(low=Min("final_price"))["low"]
    )
    models_word = plural_uk_form(count, "модель,моделі,моделей")
    text = f"Усі килими mr.Carpet на одній сторінці: {count} {models_word}"
    if low:
        # Floor, not round: "від 861" for a real 860.60 would be untrue.
        # round(.., 2) first so float noise (849.9999) does not lose a hryvnia.
        text += f", ціни від {int(round(low, 2))} грн"
    return text + ". Українські та турецькі виробники, доставка по всій Україні."


def all_collection(request):
    """Сторінка «Вся колекція» — усі товари з фільтрами (без прив'язки до категорії)."""
    from django.urls import reverse

    from project.seo_content import get_seo_guides
    from project.seo_jsonld import breadcrumb_graph, dumps_jsonld

    base_products = Product.objects.all()

    # Сортування
    products = _apply_product_sort(base_products, request.GET.get('sort'))

    # Фільтри
    filter_set = ProductFilter(request.GET, products)
    products = filter_set.qs

    # Доступні фільтри (фасети) — рахуємо з базового набору, щоб вибір одного
    # значення фасета не ховав інші його значення
    available_filters = get_available_filters(base_products, request.GET)
    products_count = products.count()

    # Пагінація
    paginator = Paginator(products, 12)
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
            "categorie": None,
            "is_collection": True,
            "collection_title": "Вся колекція",
            "collection_h1": "Вся колекція килимів",
            "collection_meta_title": COLLECTION_META_TITLE,
            "collection_meta_description": _collection_meta_description(base_products),
            "products_count": products_count,
            "products": products,
            "available_filters": available_filters,
            "current_filters": request.GET,
            "seo_guides": get_seo_guides(),
            "breadcrumb_jsonld": dumps_jsonld(
                breadcrumb_graph(
                    request,
                    [
                        ("Головна", "/"),
                        ("Вся колекція", reverse("all_collection")),
                    ],
                )
            ),
        },
    )


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
            'is_new': product.is_novelty,
            'has_discount': product.has_discount
        })
    
    return JsonResponse(results, safe=False)


# @login_required
def favourites(request):
    # favourite = Favourite.objects.get(user=request.user)
    # f_products = favourite.product.all()[::-1]
    # favorites = FavouriteProducts.objects.filter(favourite=favourite)
    return render(request, "favorite.html")


def _variant_links_context(product) -> dict:
    """Links to the other shapes and colours of this model (server-rendered).

    A failure here must never take the product page down with it: the block
    is a help for Google and shoppers, the page is the sale.
    """
    from catalog.services.product_variants import (
        shape_label,
        shape_phrase,
        variant_links,
    )

    try:
        links = variant_links(product)
        own_shape = shape_label(product)
    except Exception:  # pragma: no cover - defensive
        import logging

        logging.getLogger(__name__).exception(
            "variant links failed for product %s", product.pk
        )
        return {"variant_links": []}
    return {
        "variant_links": links,
        "variant_own_shape_phrase": shape_phrase(own_shape),
        "variant_has_other_shapes": any(
            link.shape and link.shape != own_shape for link in links
        ),
    }


def _selected_size_attr(request, product: Product):
    """Size from `?size=<ProductAttribute.pk>` (Merchant feed variant links),
    else the default one. Only fixed sizes of this product are accepted;
    anything else falls back silently, so a stale feed link never breaks."""
    raw = (request.GET.get("size") or "").strip()
    if raw.isdigit():
        attr = (
            product.product_attr.filter(pk=int(raw), custom_attribute=False)
            .select_related("size")
            .first()
        )
        if attr is not None:
            return attr
    return product.get_default_size_attr()


def _related_products(product, category, variant_ctx) -> list:
    """Products for «Схожі товари»: the hand-picked ones, else automatic.

    Hand-picked RelatedProduct rows always win. Without them the slider used
    to vanish, and most product pages linked to no other product at all.
    Like the variant block, a failure here must not take the page down.
    """
    manual = [
        rp.product
        for rp in product.related_products.select_related("product").order_by("pk")
    ]
    if manual:
        return manual
    try:
        siblings = {link.product.pk for link in variant_ctx.get("variant_links", [])}
        return auto_related_products(product, category=category, exclude=siblings)
    except Exception:  # pragma: no cover - defensive
        import logging

        logging.getLogger(__name__).exception(
            "auto related products failed for product %s", product.pk
        )
        return []


def product(request, slug):
    from django.urls import reverse

    from project.seo_jsonld import (
        breadcrumb_graph,
        dumps_jsonld,
        product_graph,
    )

    product = get_object_or_404(Product, slug=slug)
    images = ProductImage.objects.filter(product=product).order_by("sort_order", "id")

    # Room/purpose category first («Для ванни» over «Турецькі»), same chain as
    # the category page: Головна > Каталог > категорія > товар.
    category = primary_category(product)
    crumbs = [("Головна", "/"), ("Каталог", reverse("catalog"))]
    if category:
        crumbs.append((category.title, category.get_absolute_url()))
    crumbs.append((product.title, product.get_absolute_url()))

    selected_attr = _selected_size_attr(request, product)
    # Only an explicit `?size=` narrows the JSON-LD to one Offer; the bare
    # URL keeps every size (the default size is a UI choice, not a variant).
    explicit_size = selected_attr is not None and (
        (request.GET.get("size") or "").strip() == str(selected_attr.pk)
    )
    product_ld = product_graph(
        request,
        product,
        images=images,
        selected_attr=selected_attr if explicit_size else None,
    )
    variant_ctx = _variant_links_context(product)
    context = {
        "product": product,
        "breadcrumb_category": category,
        "related_products": _related_products(product, category, variant_ctx),
        # only moderated reviews are public (the API accepts anonymous posts as PENDING)
        "approved_reviews": list(
            product.reviews.filter(status="approved").order_by("-created")
        ),
        "selected_size_attr": selected_attr,
        "images": images,
        **variant_ctx,
        "ar_ready": product.ar_status == Product.AR_STATUS_READY
        and bool(product.ar_texture),
        "breadcrumb_jsonld": dumps_jsonld(breadcrumb_graph(request, crumbs)),
        "analytics_view_item": _analytics_view_item_payload(product, selected_attr),
        **_review_invite_context(request),
    }
    if product_ld:
        context["product_jsonld"] = dumps_jsonld(product_ld)
    return render(request, "product.html", context)


def product_ar_glb(request, slug):
    """Return URL (or file) for carpet GLB at given size metres."""
    from catalog.services.ar_glb_cache import get_or_build_glb, media_url_for_glb
    from catalog.services.parse_size import SizeParseError, parse_size_label

    try:
        product = Product.objects.get(slug=slug)
    except Product.DoesNotExist:
        return JsonResponse({"success": False, "error": "Товар не знайдено"}, status=404)

    if product.ar_status != Product.AR_STATUS_READY or not product.ar_texture:
        return JsonResponse(
            {"success": False, "error": "AR-текстура не готова"},
            status=404,
        )

    w_raw = request.GET.get("w")
    l_raw = request.GET.get("l")
    size_label = request.GET.get("size")

    try:
        if w_raw is not None and l_raw is not None:
            from decimal import Decimal

            width = Decimal(str(w_raw).replace(",", "."))
            length = Decimal(str(l_raw).replace(",", "."))
        elif size_label:
            width, length = parse_size_label(size_label)
        else:
            return JsonResponse(
                {"success": False, "error": "Вкажіть w і l або size"},
                status=400,
            )
        path = get_or_build_glb(product, width, length)
    except SizeParseError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)

    return JsonResponse(
        {
            "success": True,
            "glb_url": media_url_for_glb(path),
            "width": float(width),
            "length": float(length),
        }
    )


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

def _review_invite_context(request) -> dict:
    """
    Open the review modal when the URL asks for it, prefilled when it can be.

    Two shapes of link, and both have to work:

    * `?review=1` — a plain link anyone can paste anywhere. Opens the form.
    * `?review=<token>` — the one in the invitation email. Opens the form and
      fills in the name and email, so the person who already told us who they
      are is not asked twice. Every extra field is a reason to close the tab.

    An expired or forged token degrades to the plain case rather than to an
    error page: the visitor still gets to write a review, it simply will not
    count as a verified purchase.
    """
    raw = (request.GET.get("review") or "").strip()
    if not raw:
        return {"open_review_modal": False}

    context = {"open_review_modal": True, "review_name": "", "review_email": ""}
    if raw in ("1", "true", "yes"):
        return context

    from order.review_request import read_token

    order = read_token(raw)
    if order:
        context["review_name"] = (order.name or "").strip()
        context["review_email"] = (order.email or "").strip()
        context["review_token"] = raw
    return context
