from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Product, Favourite, FavouriteProducts, ProductCategory

# Create your views here.
def catalog_detail(request, slug):
    categorie = ProductCategory.objects.get(slug=slug)
    return render(request, 'catalog_inside_new.html', {'categorie': categorie})

def catalog(request):
    products = Product.objects.all()
    return render(request, 'catalog_new.html', {'products': products})

@login_required
def favourites(request):
    # favourite = Favourite.objects.get(user=request.user)
    # f_products = favourite.product.all()[::-1]
    # favorites = FavouriteProducts.objects.filter(favourite=favourite)
    return render(request, 'favorite_new.html')