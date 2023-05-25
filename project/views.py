from django.shortcuts import render
from catalog.models import ProductCategory, Product, ProductAttribute
from blog.models import Article

# Create your views here.
def index(request):
    # categories = ProductCategory.objects.all()
    products = Product.objects.all()[::-1]
    posts = Article.objects.all()[::-1]
    return render(request, 'index_new.html', context={'products': products, 'posts': posts})