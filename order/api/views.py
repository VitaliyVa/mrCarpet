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
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        cart = get_cart(request)
        
        # Обробка старого формату даних (payment_method -> payment_type)
        if 'payment_method' in data and 'payment_type' not in data:
            payment_method = data.pop('payment_method')
            if payment_method == 'card':
                data['payment_type'] = 'liqpay'
            else:
                data['payment_type'] = 'cash'
        
        # Обробка name якщо воно містить повне ім'я (старий формат)
        if 'name' in data and 'surname' not in data:
            full_name = data.get('name', '').strip()
            if ' ' in full_name:
                name_parts = full_name.split(' ', 1)
                data['name'] = name_parts[0]
                data['surname'] = name_parts[1] if len(name_parts) > 1 else name_parts[0]
            else:
                # Якщо немає пробілу, використовуємо name як surname
                data['surname'] = data['name']
        
        # Видаляємо зайві поля, які не потрібні для моделі Order
        data.pop('products', None)
        data.pop('settlement_ref', None)
        data.pop('warehouse_ref', None)
        data.pop('warehouse_title', None)
        data.pop('city', None)  # city вже включений в address
        
        # Отримуємо email та ім'я з користувача, якщо він залогінений
        if request.user.is_authenticated:
            user_email = request.user.email
            # Якщо email не передано, використовуємо email користувача
            if 'email' not in data or not data.get('email'):
                data['email'] = user_email
            # Якщо surname не передано, використовуємо last_name користувача або name
            if 'surname' not in data or not data.get('surname'):
                if hasattr(request.user, 'last_name') and request.user.last_name:
                    data['surname'] = request.user.last_name
                elif 'name' in data and data.get('name'):
                    # Якщо last_name немає, використовуємо name як surname
                    data['surname'] = data.get('name')
        else:
            # Якщо користувач не залогінений і email не передано, створюємо тимчасовий
            if 'email' not in data or not data.get('email'):
                data['email'] = f"guest_{cart.id}@temp.com"
            # Якщо surname не передано, використовуємо name
            if 'surname' not in data or not data.get('surname'):
                if 'name' in data and data.get('name'):
                    data['surname'] = data.get('name')
        
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
                cart.save()
                
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
                    cart.save()
                    
                    return Response(
                        {"success": True, "redirect_url": "/payment/"},
                        status=status.HTTP_201_CREATED
                    )
                elif order.payment_type == "cash":
                    order.save()
                    cart.ordered = True
                    cart.apply_quantity()
                    cart.save()
                    return Response(
                        {
                            "success": True,
                            "message": "Замовлення успішно оформлено!",
                            "order_number": order.order_number
                        },
                        status=status.HTTP_201_CREATED
                    )
                else:
                    raise ValueError("Неправильний спосіб оплати.")
        except ValueError as e:
            return Response(
                {"message": str(e), "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValidationError as e:
            error_message = ''.join(e.messages) if hasattr(e, 'messages') else str(e)
            return Response(
                {"message": error_message, "error": error_message},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"message": f"Помилка при створенні замовлення: {str(e)}", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
