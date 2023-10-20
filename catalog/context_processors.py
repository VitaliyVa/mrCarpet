from .models import Favourite, ProductCategory
from .utils import get_favourite

def context(request):
    categories = ProductCategory.objects.all()
    f_products = get_favourite(request).product.all()[::-1]
    # f_products = favourite.product.all()[::-1]
    context = {
        'favourites': f_products,
        'categories': categories
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