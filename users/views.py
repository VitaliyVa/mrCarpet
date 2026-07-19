import logging

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

logger = logging.getLogger(__name__)


# Create your views here.
@login_required
def profile(request):
    from project.newsletter import get_or_link_subscription_for_user

    user = request.user
    carts = Cart.objects.filter(user=user, ordered=True)
    orders = Order.objects.filter(cart__in=carts)
    sub = get_or_link_subscription_for_user(user)
    newsletter_enabled = bool(sub and sub.is_active)
    return render(
        request,
        "profile.html",
        context={
            "orders": orders,
            "newsletter_enabled": newsletter_enabled,
        },
    )


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
    logger.debug("Password reset confirm: method=%s uid=%s", request.method, uidb64)

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
            user = CustomUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist) as e:
            logger.warning(
                "Password reset confirm: bad uid or user missing (%s: %s)",
                type(e).__name__, e,
            )
            messages.error(request, 'Невірне посилання для скидання паролю')
            return render(request, 'password_reset_confirm.html', {
                'valid': False
            })
        
        # Перевіряємо токен
        token_valid = default_token_generator.check_token(user, token)

        if not token_valid:
            logger.warning("Password reset confirm: invalid/expired token for user id=%s", user.pk)
            messages.error(
                request, 
                'Токен недійсний або застарів. Запросіть нове посилання для скидання паролю.'
            )
            return render(request, 'password_reset_confirm.html', {
                'valid': False
            })
        
        # Встановлюємо новий пароль
        user.set_password(password)
        user.save()
        logger.info("Password reset confirm: password changed for user id=%s", user.pk)


        messages.success(
            request, 
            'Пароль успішно змінено! Тепер ви можете увійти з новим паролем.'
        )
        return redirect('index')
    
    # GET запит - показуємо форму
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist) as e:
        logger.warning(
            "Password reset confirm: bad uid or user missing (%s: %s)",
            type(e).__name__, e,
        )
        return render(request, 'password_reset_confirm.html', {
            'valid': False,
            'error': 'Посилання недійсне або застаріло.'
        })
    
    # Перевіряємо токен
    token_valid = default_token_generator.check_token(user, token)

    if token_valid:
        return render(request, 'password_reset_confirm.html', {
            'uidb64': uidb64,
            'token': token,
            'valid': True
        })
    else:
        logger.warning("Password reset confirm: invalid/expired token for user id=%s", user.pk)
        return render(request, 'password_reset_confirm.html', {
            'valid': False,
            'error': 'Посилання недійсне або застаріло. Запросіть нове посилання для скидання паролю.'
        })
