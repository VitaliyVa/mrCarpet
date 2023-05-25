from django.urls import path
from . import views


urlpatterns = [
    path('', views.catalog, name='catalog'),
    path('favourites/', views.favourites, name='favourites'),
    path('<str:slug>/', views.catalog_detail, name='categorie'),
]
