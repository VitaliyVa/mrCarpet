from django.urls import path
from django.contrib.staticfiles.urls import static
from django.conf import settings

from . import views

urlpatterns = [
    path('products/', views.ProductApiView.as_view(), name='products-api'),
    path('favourites/', views.FavouriteApiView.as_view(), name='favourites-api'),
    path('add_to_favourites/', views.FavouriteProductView.as_view(), name='add-to-favourites'),
    path('add_to_favourites/<int:pk>', views.FavouriteProductView.as_view(), name='remove-from-favourites')
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)