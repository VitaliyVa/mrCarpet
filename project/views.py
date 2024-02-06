from django.shortcuts import render
from catalog.models import ProductCategory, Product, ProductAttribute, ProductSale
from blog.models import Article

# Create your views here.
def index(request):
    # categories = ProductCategory.objects.all()
    products = Product.objects.all()[::-1]
    # on_sale = ProductAttribute.objects.exclude(discount=None).filter(product__in=products).values_list('product')
    # sale_products = Product.objects.filter(id__in=on_sale)
    sale_products = ProductSale.objects.first().products.all()
    posts = Article.objects.all()[::-1]
    return render(request, 'index.html', context={'products': products, 'posts': posts, 'sale_products': sale_products})


def about(request):
    return render(request, 'about.html')


def checkout(request):
    return render(request, 'checkout.html')


def delivery(request):
    return render(request, 'delivery.html')


def faq(request):
    return render(request, 'faq.html')


def refund_page(request):
    return render(request, 'refund.html')


def terms(request):
    return render(request, 'terms.html')


def policy(request):
    return render(request, 'policy.html')
