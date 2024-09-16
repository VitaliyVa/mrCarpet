from django.urls import path
from . import views


urlpatterns = [
    path('', views.catalog, name='catalog'),
    path('favourites/', views.favourites, name='favourites'),
    path('sale/', views.sale, name='sale'),
    path('categorie/<str:slug>/', views.catalog_detail, name='categorie'),
    path('product/<str:slug>/', views.product, name='product')
]
