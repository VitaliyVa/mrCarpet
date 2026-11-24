from .models import Favourite, ProductCategory, Product, FavouriteProducts
from django.db.models import Count

from .promotions import has_promo
from .utils import get_favourite_readonly


def context(request):
    # Empty categories stay out of the menu, same rule as the sitemap: a link
    # on every page to a noindex page that shows nothing.
    categories = ProductCategory.objects.annotate(
        _n=Count("products")
    ).filter(_n__gt=0)
    # f_products = get_favourite(request).product.all()[::-1]
    # raw_products = FavouriteProducts.objects.filter(favourite=get_favourite(request))[::-1]
    # f_products = [product.product for product in raw_products]
    favourite = get_favourite_readonly(request)
    f_products = favourite.product.all()[::-1] if favourite else []
    products = Product.objects.all().order_by("-id")
    # f_products = favourite.product.all()[::-1]
    context = {
        'favourites': f_products,
        'categories': categories,
        'search_products': products,
        # A callable: the template calls it only where it is used (the
        # header), and the answer is cached for a few minutes.
        'has_promo': has_promo,
    }
    # if request.user.is_authenticated:
    #     try:
    #         favourite = Favourite.objects.get(user=request.user)
    #     except:
    #         favourite = Favourite.objects.create(user=request.user)
    #     f_products = favourite.product.all()[::-1]
    #     context = {
    #         'favourites': f_products,
    #         'categories': categories,
    #     }
    # else:
    #     context = {
    #         'favourites': [],
    #         'categories': categories,
    #     }
    return context