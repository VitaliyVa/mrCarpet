from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import reverse

from cart.models import Cart
from order.models import Order
from project.email_branding import wrap_plain_email
from project.smtp_utils import send_smtp_mail
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
    Після успішного запиту показуємо окремий success-екран (без форми).
    """
    context = {
        "email_sent": False,
        "submitted_email": "",
        "form_error": "",
    }

    if request.method != "POST":
        return render(request, "password_reset.html", context)

    email = request.POST.get("email", "").strip()
    context["submitted_email"] = email

    if not email:
        context["form_error"] = "Будь ласка, введіть email адресу"
        return render(request, "password_reset.html", context)

    user = CustomUser.objects.filter(email=email).first()

    # Однаковий success-екран незалежно від існування юзера (безпека)
    if not user:
        context["email_sent"] = True
        return render(request, "password_reset.html", context)

    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = request.build_absolute_uri(
        reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    )

    subject = "Скидання паролю - mr.Carpet"
    message = (
        "Вітаємо!\n\n"
        "Ви отримали цей лист, тому що хтось запросив скидання паролю "
        "для вашого облікового запису на mr.Carpet.\n\n"
        "Якщо це були ви, перейдіть за посиланням нижче для встановлення нового паролю:\n"
        f"{reset_url}\n\n"
        "Якщо ви не запитували скидання паролю, просто проігноруйте цей лист.\n\n"
        "З повагою,\n"
        "Команда mr.Carpet"
    )
    plain, html = wrap_plain_email(
        message,
        title=subject,
        eyebrow="Безпека акаунта",
        preheader="Посилання для скидання паролю mr.Carpet",
    )

    try:
        ok = send_smtp_mail(
            subject,
            plain,
            [email],
            fail_silently=False,
            html_message=html,
        )
        if not ok:
            raise RuntimeError("SMTP send returned false")
        context["email_sent"] = True
    except Exception:
        context["form_error"] = (
            "Не вдалося надіслати лист. Спробуйте пізніше або зверніться до підтримки."
        )

    return render(request, "password_reset.html", context)


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
