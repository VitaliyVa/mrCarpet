from django.shortcuts import render
from .models import Product

# Create your views here.
def catalog_detail(request):
    product = Product.objects.first()
    specs = product.product_specs.first()
    return render(request, 'catalog.html', {'product': product, 'specs': specs})

def catalog(request):
    products = Product.objects.all()
    return render(request, 'catalog.html', {'products': products})

def favourites(request):
    favourites = Product.objects.filter(favourites=request.user)
    return render(request, 'favourites.html', {'favourites': favourites})