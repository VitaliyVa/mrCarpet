from rest_framework.generics import CreateAPIView
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from cart.utils import get_cart
from project.free_shipping import free_shipping_for_total
from .serializers import (
    ContactRequestSerializer,
    StockInquirySerializer,
    SubscriptionSerializer,
)
from ..email_utils import (
    build_contact_received_email,
    build_stock_inquiry_admin_email,
    build_stock_inquiry_customer_email,
)
from ..models import ContactRequest, SMTPSettings, StockInquiry, Subscription
from ..smtp_utils import send_smtp_mail_async
from ..telegram_utils import notify_contact, notify_stock


class ContactRequestCreateView(APIView):
    queryset = ContactRequest.objects.all()
    serializer_class = ContactRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = ContactRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from_email = serializer.save()
        subject, plain, html = build_contact_received_email(from_email)
        send_smtp_mail_async(
            subject,
            plain,
            [from_email.email],
            html_message=html,
        )
        notify_contact(from_email)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StockInquiryCreateView(APIView):
    """Запит про наявність розміру — зберігаємо в адмінці + лист на shop email."""

    def post(self, request, *args, **kwargs):
        serializer = StockInquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inquiry = serializer.save()

        try:
            smtp = SMTPSettings.load()
            notify_to = smtp.server_email
        except Exception:
            notify_to = None

        if notify_to:
            admin_subject, admin_text, admin_html = build_stock_inquiry_admin_email(
                inquiry
            )
            send_smtp_mail_async(
                admin_subject,
                admin_text,
                [notify_to],
                html_message=admin_html,
            )

        # Підтвердження клієнту (не блокує)
        cust_subject, cust_text, cust_html = build_stock_inquiry_customer_email(
            inquiry
        )
        send_smtp_mail_async(
            cust_subject,
            cust_text,
            [inquiry.email],
            html_message=cust_html,
        )
        notify_stock(inquiry)

        return Response(
            {"success": True, "message": "Запит надіслано. Ми скоро з вами зв’яжемось."},
            status=status.HTTP_201_CREATED,
        )


class SubscriptionCreateView(CreateAPIView):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer

    def create(self, request, *args, **kwargs):
        from project.newsletter import subscribe_email
        from project.models import Subscription as SubModel

        serializer = SubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = request.user if request.user.is_authenticated else None

        try:
            sub, status_key = subscribe_email(
                email,
                source=SubModel.SOURCE_FOOTER,
                user=user,
            )
        except ValueError as exc:
            return Response(
                {"message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        welcome = {
            "welcome_promocode": "WELCOME5",
            "welcome_discount": 5,
        }

        if status_key == "already_active":
            return Response(
                {
                    "message": "Ви уже підписані. Ось ваш промокод на −5%.",
                    **welcome,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = (
            "Підписку відновлено. Дякуємо!"
            if status_key == "reactivated"
            else "Ви успішно підписалися на розсилку новин та акцій."
        )
        return Response(
            {
                "email": sub.email,
                "is_active": sub.is_active,
                "message": message,
                **welcome,
            },
            status=status.HTTP_201_CREATED,
        )


@api_view(['POST'])
def check_promocode(request):
    """Перевірка промокоду та застосування знижки"""
    promocode = request.data.get('promocode')

    if not promocode:
        return Response(
            {'error': 'Промокод не вказано'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        from catalog.promocode import PromoCodeError, resolve_and_validate

        email = request.data.get('email') or ''
        if request.user.is_authenticated and not email:
            email = request.user.email or ''

        promo = resolve_and_validate(
            promocode,
            user=request.user if request.user.is_authenticated else None,
            email=email,
            require_identity=False,
        )

        cart = get_cart(request)
        original_price = cart.get_total_price()
        discount_amount = original_price * (promo.discount / 100)
        final_price = original_price - discount_amount

        if hasattr(request, 'session'):
            request.session['applied_promocode'] = promo.code

        return Response({
            'success': True,
            'message': f'Промокод застосовано! Знижка: {promo.discount}%',
            'original_price': original_price,
            'discount_percent': promo.discount,
            'discount_amount': discount_amount,
            'final_price': final_price,
            'promocode': promo.code,
            'free_shipping': free_shipping_for_total(final_price),
        })

    except PromoCodeError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception:
        return Response(
            {'error': 'Помилка при перевірці промокоду'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
