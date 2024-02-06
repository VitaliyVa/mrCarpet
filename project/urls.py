from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('checkout/', views.checkout, name='checkout'),
    path('delivery/', views.delivery, name='delivery'),
    path('faq/', views.faq, name='faq'),
    path('refund/', views.refund_page, name='refund'),
    path('terms/', views.terms, name='terms'),
    path('policy/', views.policy, name='policy'),
]
