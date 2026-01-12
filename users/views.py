from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings

from cart.models import Cart
from order.models import Order
from .models import CustomUser


# Create your views here.
@login_required
def profile(request):
    user = request.user
    carts = Cart.objects.filter(user=user, ordered=True)
    orders = Order.objects.filter(cart__in=carts)
    return render(request, "profile.html", context={"orders": orders})


def password_reset_view(request):
    """
    Відображення сторінки відновлення паролю та обробка POST запиту.
    """
    print("=" * 50)
    print("[PASSWORD RESET] Запит отримано")
    print(f"[PASSWORD RESET] Method: {request.method}")
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        print(f"[PASSWORD RESET] Email отримано: {email}")
        
        if not email:
            print("[PASSWORD RESET] Помилка: email порожній")
            messages.error(request, 'Будь ласка, введіть email адресу')
            return render(request, 'password_reset.html')
        
        try:
            user = CustomUser.objects.get(email=email)
            print(f"[PASSWORD RESET] Користувач знайдено: {user.email} (ID: {user.id})")
        except CustomUser.DoesNotExist:
            print(f"[PASSWORD RESET] Користувача з email {email} не знайдено")
            # Не повідомляємо, що користувача не існує (безпека)
            messages.success(
                request, 
                'Якщо користувач з таким email існує, ми надіслали інструкції на пошту'
            )
            return render(request, 'password_reset.html')
        
        # Генеруємо токен для скидання паролю
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        print(f"[PASSWORD RESET] Токен згенеровано: {token[:20]}...")
        print(f"[PASSWORD RESET] UID (base64): {uid}")
        
        # Формуємо URL для скидання паролю
        reset_url = request.build_absolute_uri(
            reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        )
        print(f"[PASSWORD RESET] Reset URL: {reset_url}")
        
        # Відправляємо email
        try:
            print("[PASSWORD RESET] Початок відправки email...")
            print(f"[PASSWORD RESET] EMAIL_HOST: {settings.EMAIL_HOST}")
            print(f"[PASSWORD RESET] EMAIL_PORT: {settings.EMAIL_PORT}")
            print(f"[PASSWORD RESET] EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
            print(f"[PASSWORD RESET] EMAIL_USE_SSL: {getattr(settings, 'EMAIL_USE_SSL', False)}")
            print(f"[PASSWORD RESET] EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
            print(f"[PASSWORD RESET] DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
            print(f"[PASSWORD RESET] Recipient: {email}")
            
            subject = "Скидання паролю - MrCarpet"
            message = f"""
Вітаємо!

Ви отримали цей лист, тому що хтось запросив скидання паролю для вашого облікового запису на MrCarpet.

Якщо це були ви, перейдіть за посиланням нижче для встановлення нового паролю:
{reset_url}

Якщо ви не запитували скидання паролю, просто проігноруйте цей лист.

З повагою,
Команда MrCarpet
"""
            
            print(f"[PASSWORD RESET] Subject: {subject}")
            print(f"[PASSWORD RESET] Message length: {len(message)} символів")
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            
            print("[PASSWORD RESET] ✅ Email успішно відправлено!")
            messages.success(
                request, 
                'Інструкції для скидання паролю надіслано на вашу пошту'
            )
        except Exception as e:
            print("=" * 50)
            print("[PASSWORD RESET] ❌ ПОМИЛКА ПРИ ВІДПРАВЦІ EMAIL")
            print(f"[PASSWORD RESET] Тип помилки: {type(e).__name__}")
            print(f"[PASSWORD RESET] Повідомлення: {str(e)}")
            print("=" * 50)
            import traceback
            print("[PASSWORD RESET] Traceback:")
            traceback.print_exc()
            print("=" * 50)
            messages.error(
                request, 
                f'Помилка при відправці email: {str(e)}. Спробуйте пізніше або зверніться до підтримки.'
            )
    else:
        print("[PASSWORD RESET] GET запит - показуємо форму")
    
    print("=" * 50)
    return render(request, 'password_reset.html')


def password_reset_confirm(request, uidb64, token):
    """
    Сторінка для встановлення нового паролю після переходу за посиланням з email.
    """
    print("=" * 50)
    print("[PASSWORD RESET CONFIRM] Запит отримано")
    print(f"[PASSWORD RESET CONFIRM] Method: {request.method}")
    print(f"[PASSWORD RESET CONFIRM] UID (base64): {uidb64}")
    print(f"[PASSWORD RESET CONFIRM] Token: {token[:20]}...")
    
    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        password2 = request.POST.get('password2', '').strip()
        
        if not password or not password2:
            messages.error(request, 'Будь ласка, заповніть обидва поля')
            return render(request, 'password_reset_confirm.html', {
                'uidb64': uidb64,
                'token': token,
                'valid': True
            })
        
        if password != password2:
            messages.error(request, 'Паролі не співпадають')
            return render(request, 'password_reset_confirm.html', {
                'uidb64': uidb64,
                'token': token,
                'valid': True
            })
        
        if len(password) < 8:
            messages.error(request, 'Пароль повинен містити мінімум 8 символів')
            return render(request, 'password_reset_confirm.html', {
                'uidb64': uidb64,
                'token': token,
                'valid': True
            })
        
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            print(f"[PASSWORD RESET CONFIRM] UID декодовано: {uid}")
            user = CustomUser.objects.get(pk=uid)
            print(f"[PASSWORD RESET CONFIRM] Користувач знайдено: {user.email} (ID: {user.id})")
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist) as e:
            print(f"[PASSWORD RESET CONFIRM] ❌ Помилка декодування або користувач не знайдено: {type(e).__name__}: {str(e)}")
            messages.error(request, 'Невірне посилання для скидання паролю')
            return render(request, 'password_reset_confirm.html', {
                'valid': False
            })
        
        # Перевіряємо токен
        print("[PASSWORD RESET CONFIRM] Перевірка токену...")
        token_valid = default_token_generator.check_token(user, token)
        print(f"[PASSWORD RESET CONFIRM] Токен валідний: {token_valid}")
        
        if not token_valid:
            print("[PASSWORD RESET CONFIRM] ❌ Токен недійсний або застарів")
            messages.error(
                request, 
                'Токен недійсний або застарів. Запросіть нове посилання для скидання паролю.'
            )
            return render(request, 'password_reset_confirm.html', {
                'valid': False
            })
        
        # Встановлюємо новий пароль
        print("[PASSWORD RESET CONFIRM] Встановлення нового паролю...")
        user.set_password(password)
        user.save()
        print("[PASSWORD RESET CONFIRM] ✅ Пароль успішно змінено!")
        
        messages.success(
            request, 
            'Пароль успішно змінено! Тепер ви можете увійти з новим паролем.'
        )
        return redirect('index')
    
    # GET запит - показуємо форму
    print("[PASSWORD RESET CONFIRM] GET запит - показуємо форму")
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        print(f"[PASSWORD RESET CONFIRM] UID декодовано: {uid}")
        user = CustomUser.objects.get(pk=uid)
        print(f"[PASSWORD RESET CONFIRM] Користувач знайдено: {user.email} (ID: {user.id})")
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist) as e:
        print(f"[PASSWORD RESET CONFIRM] ❌ Помилка декодування або користувач не знайдено: {type(e).__name__}: {str(e)}")
        return render(request, 'password_reset_confirm.html', {
            'valid': False,
            'error': 'Посилання недійсне або застаріло.'
        })
    
    # Перевіряємо токен
    print("[PASSWORD RESET CONFIRM] Перевірка токену...")
    token_valid = default_token_generator.check_token(user, token)
    print(f"[PASSWORD RESET CONFIRM] Токен валідний: {token_valid}")
    
    if token_valid:
        print("[PASSWORD RESET CONFIRM] ✅ Токен валідний, показуємо форму")
        return render(request, 'password_reset_confirm.html', {
            'uidb64': uidb64,
            'token': token,
            'valid': True
        })
    else:
        print("[PASSWORD RESET CONFIRM] ❌ Токен недійсний")
        return render(request, 'password_reset_confirm.html', {
            'valid': False,
            'error': 'Посилання недійсне або застаріло. Запросіть нове посилання для скидання паролю.'
        })
    
    print("=" * 50)
