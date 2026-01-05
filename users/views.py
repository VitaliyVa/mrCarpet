from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages

from cart.models import Cart
from order.models import Order


# Create your views here.
@login_required
def profile(request):
    user = request.user
    carts = Cart.objects.filter(user=user, ordered=True)
    orders = Order.objects.filter(cart__in=carts)
    return render(request, "profile.html", context={"orders": orders})


def password_reset_view(request):
    """
    Відображення сторінки відновлення паролю.
    
    Бекендер має додати логіку для:
    - Перевірки існування користувача з email
    - Генерації токену для скидання паролю
    - Відправки email з посиланням
    """
    if request.method == 'POST':
        email = request.POST.get('email')
        
        # TODO: Додати логіку відправки email
        # Приклад:
        # try:
        #     user = User.objects.get(email=email)
        #     # Генерація токену
        #     # Відправка email
        #     messages.success(request, 'Лист з інструкціями надіслано на вашу пошту')
        #     return redirect('password_reset')
        # except User.DoesNotExist:
        #     messages.error(request, 'Користувача з таким email не знайдено')
        
        messages.info(request, f'Email отримано: {email}. Додайте логіку обробки.')
    
    return render(request, 'password_reset.html')
