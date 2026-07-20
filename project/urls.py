from django.urls import path, re_path
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
    path(
        'unsubscribe/preview/',
        views.newsletter_unsubscribe_preview,
        name='newsletter_unsubscribe_preview',
    ),
    path(
        'unsubscribe/<uuid:token>/',
        views.newsletter_unsubscribe,
        name='newsletter_unsubscribe',
    ),
    path('success/', views.success, name='success'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path(
        'google67459f697e641b7f.html',
        views.google_site_verification_file,
        name='google_site_verification_file',
    ),
    re_path(
        r'^(?P<filename>tiktok[A-Za-z0-9]+\.txt)$',
        views.tiktok_site_verification_file,
        name='tiktok_site_verification_file',
    ),
]
