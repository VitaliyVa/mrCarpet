from django.urls import path
from django.contrib.auth.views import LogoutView

from .views import profile, password_reset_view, password_reset_confirm

urlpatterns = [
    path('profile/', profile, name='profile'),
    path('logout/', LogoutView.as_view(next_page="/"), name="logout"),
    path('password-reset/', password_reset_view, name='password_reset'),
    path('password-reset-confirm/<uidb64>/<token>/', password_reset_confirm, name='password_reset_confirm'),
]