from .models import Favourite


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