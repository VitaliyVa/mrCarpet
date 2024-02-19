from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from cart.models import Cart
from order.models import Order


# Create your views here.
@login_required
def profile(request):
    user = request.user
    carts = Cart.objects.filter(user=user, ordered=True)
    orders = Order.objects.filter(cart__in=carts)
    return render(request, "profile.html", context={"orders": orders})
