from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .filters import ProductFilter
from .models import (
    Product,
    Favourite,
    FavouriteProducts,
    ProductCategory,
    ProductAttribute,
    Size, ProductImage,
)

from django.core.paginator import Paginator

from .utils import get_attributes


def get_paginator(products: Product, request):
    paginator = Paginator(products, settings.MAX_PAGE_SIZE)
    paginator.allow_empty_first_page = True
    page = request.GET.get('page')
    if not page or not page.isdigit():
        page = 1
    else:
        page = int(page)

    page_obj = paginator.page(page)

    return paginator, page_obj



# Create your views here.
def catalog_detail(request, slug):
    categorie = ProductCategory.objects.get(slug=slug)
    filter_set = ProductFilter(request.GET, categorie.products.all())
    products = filter_set.qs
    paginator, page_obj = get_paginator(products, request)
    sizes = get_attributes(products=products)

    return render(
        request,
        "catalog_inside.html",
        {"categorie": categorie,'paginator':paginator,'page_obj':page_obj, "products": products, "sizes": sizes},
    )

def sale(request):
    products = Product.objects.filter(product_sale__isnull=False)
    filter_set = ProductFilter(request.GET, products)
    products = filter_set.qs
    paginator, page_obj = get_paginator(products, request)

    sizes = get_attributes(products=products)
    return render(
        request,
        "sale_inside.html",
        {
         'products': products,
         "paginator": paginator,
         'page_obj':page_obj,
         "sizes": sizes
        },
    )


def catalog(request):
    products = Product.objects.all()
    # filter_set = ProductFilter(request.GET, products)
    # products = filter_set.qs
    return render(request, "catalog.html", {"products": products})


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
