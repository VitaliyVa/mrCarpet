from django.urls import path, include
from django.contrib.staticfiles.urls import static
from django.conf import settings

from rest_framework.routers import DefaultRouter

from . import views


router = DefaultRouter()
router.register(r"product-reviews", views.ProductReviewViewSet, basename="product_reviews")
router.register(r"favourite-products", views.FavouriteProductViewSet, basename="favourite_products")
router.register(r"sale", views.SaleProductsViewSet, basename="sale")
router.register("products", views.ProductViewSet, basename="products")
router.register("categories", views.ProductCategoryViewSet, basename="categories")

urlpatterns = [
    # path('products/', views.ProductApiView.as_view(), name='products-api'),
    # path('favourites/', views.FavouriteApiView.as_view(), name='favourites-api'),
    # path('add_to_favourites/', views.FavouriteProductView.as_view(), name='add-to-favourites'),
    # path('add_to_favourites/<int:pk>', views.FavouriteProductView.as_view(), name='remove-from-favourites'),
    path('', include(router.urls)),
    path('add-promocode/', views.apply_promocode, name="promocode")
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)