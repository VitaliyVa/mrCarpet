from django.db.models import QuerySet

from .models import Favourite, Product, ProductAttribute, Size


def get_attributes(products: QuerySet[Product]):
    # attributes = ProductAttribute.objects.filter(product__in=products)
    sizes = Size.objects.filter(product_attr__product__in=products).distinct()
    return sizes

def get_favourite(request) -> Favourite:
    if request.user.is_authenticated:
        try:
            favourite = Favourite.objects.get(user=request.user)
        except:
            favourite = Favourite.objects.create(user=request.user)
    else:
        try:
            fav_id = request.session.get("fav_id")
            favourite = Favourite.objects.get(id=fav_id)
        except:
            favourite = Favourite.objects.create()
            request.session["fav_id"] = favourite.id
    return favourite