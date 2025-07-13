from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status

from django.shortcuts import redirect
from django.db import transaction
from django.core.exceptions import ValidationError

from cart.utils import get_cart
from catalog.models import PromoCode
from ..models import Order
from .serializers import OrderSerializer


class OrderCreateViewSet(mixins.CreateModelMixin, GenericViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def create(self, request, *args, **kwargs):
        try:
            request.data._mutable = True
        except:
            "it is not a drf request"
        data = request.data
        cart = get_cart(request)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        
        # Отримуємо промокод з запиту або з сесії
        promo = serializer.validated_data.pop("promocode", None)
        
        # Якщо промокод не передано в запиті, перевіряємо чи є застосований промокод
        if not promo and hasattr(request, 'session'):
            promo = request.session.get("applied_promocode")
        
        # Розраховуємо загальну ціну
        total_price = cart.get_total_price()
        
        try:
            with transaction.atomic():
                order = Order.objects.create(**serializer.validated_data)
                cart.order = order
                
                if promo:
                    try:
                        promocode = PromoCode.objects.get(code=promo)
                        order.promocode = promocode
                        # Розраховуємо ціну зі знижкою
                        order.total_price = float(cart.get_total_price(promo=promocode.discount))
                        # Очищаємо промокод з сесії
                        if hasattr(request, 'session'):
                            request.session.pop("applied_promocode", None)
                    except PromoCode.DoesNotExist:
                        raise ValueError("Неправильний промокод.")
                else:
                    order.total_price = float(total_price)
                
                if order.payment_type == "liqpay":
                    order.status = "Не оплачено"
                    order.save()
                    cart.apply_quantity()
                    return redirect("payment")
                elif order.payment_type == "cash":
                    order.save()
                    cart.ordered = True
                    cart.apply_quantity()
                else:
                    raise ValueError("Неправильний спосіб оплати.")
        except ValueError as e:
            return Response(
                {"message": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValidationError as e:
            return Response(
                {"message": ''.join(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
