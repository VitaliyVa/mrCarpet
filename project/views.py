from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import F, Count, Case, When, Value, IntegerField, Sum
from catalog.models import ProductCategory, Product, ProductAttribute, ProductSale
from blog.models import Article
from cart.utils import get_cart

# Create your views here.
def index(request):
    # categories = ProductCategory.objects.all()
    products = Product.objects.all()
    # products = (
    #     Product.objects.annotate(
    #         total_quantity=Sum("product_attr__quantity"),
    #         has_attribute_with_quantity_gt_zero=Case(
    #             When(total_quantity__gt=0, then=1),
    #             When(total_quantity=0, then=2),
    #             output_field=IntegerField(),
    #         )
    #     )
    #     .filter(has_attribute_with_quantity_gt_zero__gt=0)
    #     .order_by("has_attribute_with_quantity_gt_zero", "-created")
    # )
    print(products)
    # on_sale = ProductAttribute.objects.exclude(discount=None).filter(product__in=products).values_list('product')
    # sale_products = Product.objects.filter(id__in=on_sale)
    try:
        main_sale_date = ProductSale.objects.get(main_sale=True).date_end
        sale_products = ProductSale.objects.first().products.all()
    except:
        main_sale_date = None
        sale_products = []
    posts = Article.objects.all()[::-1]
    return render(request, 'index.html', context={'products': products, 'posts': posts, 'sale_products': sale_products, 'main_sale_date': main_sale_date})


def about(request):
    return render(request, 'about.html')


def checkout(request):
    cart = get_cart(request)
    context = {
        'cart': cart,
    }
    return render(request, 'checkout.html', context)


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

def success(request):
    return render(request, 'success.html')

def reset_password(request):
    return render(request, 'reset_password.html')


def robots_txt(request):
    """
    DEV robots: повна заборона індексації, поки сайт у розробці.

    PROD (НЕ вмикати без явного рішення / Фаза 8 у docs/seo-ai-search-roadmap.md):

        User-agent: *
        Allow: /
        Disallow: /admin/
        Disallow: /api/
        Disallow: /basket/
        Disallow: /checkout/
        Disallow: /payment/
        Disallow: /profile/
        Disallow: /success/
        Sitemap: https://mrcarpet24.com/sitemap.xml

        # AI crawlers (GEO): на проді не блокувати зайво GPTBot / ClaudeBot / PerplexityBot
        # якщо Allow: / вже відкриває сайт.
    """
    # ASCII-only body: robots.txt + Windows text/plain без charset легко ламає кирилицю
    robots_content = (
        "# DEV: site under development -- full disallow\n"
        "# Go-live: replace with prod rules from docs/seo-ai-search-roadmap.md (Phase 8)\n"
        "User-agent: *\n"
        "Disallow: /\n"
    )
    return HttpResponse(robots_content, content_type="text/plain; charset=utf-8")
