from .models import Favourite, ProductCategory

def context(request):
    categories = ProductCategory.objects.all()
    if request.user.is_authenticated:
        favourite = Favourite.objects.get(user=request.user)
        f_products = favourite.product.all()[::-1]
        context = {
            'favourites': f_products,
            'categories': categories,
        }
    else:
        context = {
            'favourites': [],
            'categories': categories,
        }
    return context