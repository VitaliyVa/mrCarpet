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


# Create your views here.
def catalog_detail(request, slug):
    categorie = ProductCategory.objects.get(slug=slug)
    filter_set = ProductFilter(request.GET, categorie.products.all())
    products = filter_set.qs
    sizes = Size.objects.all()
    return render(
        request,
        "catalog_inside.html",
        {"categorie": categorie, "products": products, "sizes": sizes},
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


def stock(request):
    products = Product.objects.filter(has_discount=True)
    return render(request, "catalog.html", {"products": products})