from rest_framework.generics import CreateAPIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from catalog.models import PromoCode
from cart.utils import get_cart

from .serializers import ContactRequestSerializer, SubscriptionSerializer
from ..models import ContactRequest, Subscription


class ContactRequestCreateView(CreateAPIView):
    queryset = ContactRequest.objects.all()
    serializer_class = ContactRequestSerializer


class SubscriptionCreateView(CreateAPIView):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer

    def create(self, request, *args, **kwargs):
        if Subscription.objects.filter(email=request.data["email"]).exists():
            return Response(
                {"message": "Ви уже підписані."},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            serializer.data, status=status.HTTP_201_CREATED
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
        # Перевіряємо чи існує промокод та чи не закінчився термін дії
        promo = PromoCode.objects.get(
            code=promocode,
            end_time__gt=timezone.now()
        )
        
        # Отримуємо корзину користувача
        cart = get_cart(request)
        
        # Розраховуємо ціну зі знижкою
        original_price = cart.get_total_price()
        discount_amount = original_price * (promo.discount / 100)
        final_price = original_price - discount_amount
        
        # Зберігаємо промокод в сесії для подальшого використання
        if hasattr(request, 'session'):
            request.session['applied_promocode'] = promocode
        
        return Response({
            'success': True,
            'message': f'Промокод застосовано! Знижка: {promo.discount}%',
            'original_price': original_price,
            'discount_percent': promo.discount,
            'discount_amount': discount_amount,
            'final_price': final_price,
            'promocode': promocode
        })
        
    except PromoCode.DoesNotExist:
        return Response(
            {'error': 'Промокод не знайдено або термін дії закінчився'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': 'Помилка при перевірці промокоду'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
