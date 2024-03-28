from django.urls import path
from django.contrib.auth.views import LogoutView

from .views import profile

urlpatterns = [
    path('profile/', profile, name='profile'),
    path('logout/', LogoutView.as_view(next_page="/"), name="logout"),
]