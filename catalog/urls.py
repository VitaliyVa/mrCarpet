from django.urls import path
from . import views


urlpatterns = [
    path('', views.catalog, name='catalog'),
    path('collection/', views.all_collection, name='all_collection'),
    path('favourites/', views.favourites, name='favourites'),
    path('categorie/<str:slug>/', views.catalog_detail, name='categorie'),
    path('product/<str:slug>/', views.product, name='product'),
    path('stock/', views.stock, name='stock'),
    path('api/search/', views.search_products, name='search_products'),
]
