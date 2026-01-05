from django.urls import path
from django.contrib.auth.views import LogoutView

from .views import profile, password_reset_view

urlpatterns = [
    path('profile/', profile, name='profile'),
    path('logout/', LogoutView.as_view(next_page="/"), name="logout"),
    path('password-reset/', password_reset_view, name='password_reset'),
]