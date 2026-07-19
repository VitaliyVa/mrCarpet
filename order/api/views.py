from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status

from django.db import transaction
from django.core.exceptions import ValidationError

from cart.utils import get_cart
from catalog.promocode import PromoCodeError, apply_promocode_to_order
from project.free_shipping import free_shipping_for_total
from project.ga4_ecommerce import purchase_payload
from project.telegram_utils import enqueue_order_telegram
from ..models import Order
from ..email_utils import enqueue_order_confirmation_email
from .serializers import OrderSerializer


class OrderCreateViewSet(mixins.CreateModelMixin, GenericViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        cart = get_cart(request)

        if "payment_method" in data and "payment_type" not in data:
            payment_method = data.pop("payment_method")
            if payment_method == "card":
                data["payment_type"] = Order.PAYMENT_LIQPAY
            else:
                data["payment_type"] = Order.PAYMENT_CASH

        if "name" in data and "surname" not in data:
            full_name = data.get("name", "").strip()
            if " " in full_name:
                name_parts = full_name.split(" ", 1)
                data["name"] = name_parts[0]
                data["surname"] = name_parts[1] if len(name_parts) > 1 else name_parts[0]
            else:
                data["surname"] = data["name"]

        city = (data.get("city") or "").strip()
        if city:
            data["city"] = city

        data.pop("products", None)
        data.pop("settlement_ref", None)
        data.pop("warehouse_ref", None)
        data.pop("warehouse_title", None)

        email = (data.get("email") or "").strip()
        if request.user.is_authenticated:
            if not email:
                email = request.user.email or ""
                data["email"] = email
            if not data.get("surname"):
                if getattr(request.user, "last_name", None):
                    data["surname"] = request.user.last_name
                elif data.get("name"):
                    data["surname"] = data.get("name")
        else:
            if not data.get("surname") and data.get("name"):
                data["surname"] = data.get("name")

        if not email or email.endswith("@temp.com"):
            return Response(
                {
                    "message": "Вкажіть коректний email для підтвердження замовлення",
                    "email": ["Вкажіть коректний email"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        data["email"] = email

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        promo = serializer.validated_data.pop("promocode", None)

        if not promo and hasattr(request, "session"):
            promo = request.session.get("applied_promocode")

        total_price = cart.get_total_price()

        try:
            # Важливо: жодного мережевого I/O (SMTP) всередині atomic —
            # на SQLite це тримає exclusive lock і дає "database is locked".
            with transaction.atomic():
                order = Order.objects.create(**serializer.validated_data)
                cart.order = order
                cart.save(update_fields=["order"])

                if promo:
                    try:
                        promocode = apply_promocode_to_order(
                            order,
                            promo,
                            user=(
                                request.user
                                if request.user.is_authenticated
                                else None
                            ),
                        )
                        order.total_price = float(
                            cart.get_total_price(promo=promocode.discount)
                        )
                        if hasattr(request, "session"):
                            request.session.pop("applied_promocode", None)
                    except PromoCodeError as exc:
                        raise ValueError(str(exc)) from exc
                else:
                    order.total_price = float(total_price)

                fs = free_shipping_for_total(order.total_price)
                order.free_shipping = fs["qualifies"]
                order.free_shipping_threshold = (
                    fs["threshold"] if fs["qualifies"] else None
                )

                if order.payment_type == Order.PAYMENT_LIQPAY:
                    order.status = Order.STATUS_AWAITING_PAYMENT
                    order.save()
                    cart.apply_quantity()
                    cart.save()
                    payment_type = order.payment_type
                    order_number = order.order_number
                elif order.payment_type == Order.PAYMENT_CASH:
                    order.status = Order.STATUS_NEW
                    order.save()
                    cart.ordered = True
                    cart.apply_quantity()
                    cart.save()
                    payment_type = order.payment_type
                    order_number = order.order_number
                else:
                    raise ValueError("Неправильний спосіб оплати.")

            # Лист / Telegram у фоні після commit — API не чекає зовнішні сервіси
            if payment_type == Order.PAYMENT_CASH:
                enqueue_order_confirmation_email(order.pk)
                enqueue_order_telegram(order.pk, event="new")
            elif payment_type == Order.PAYMENT_LIQPAY:
                enqueue_order_telegram(order.pk, event="awaiting_payment")

            analytics_purchase = None
            try:
                analytics_purchase = purchase_payload(order, cart)
                if hasattr(request, "session"):
                    request.session["ga4_purchase"] = analytics_purchase
            except Exception:
                analytics_purchase = None

            # Server-side purchase (Measurement Protocol). Cash now; LiqPay on paid callback.
            if payment_type == Order.PAYMENT_CASH:
                try:
                    from project.ga4_mp import (
                        client_id_from_ga_cookie,
                        enqueue_order_purchase_mp,
                    )

                    cid = client_id_from_ga_cookie(request.COOKIES.get("_ga"))
                    enqueue_order_purchase_mp(order.pk, client_id=cid)
                except Exception:
                    pass

            # Purchase payload stays in session only — /success/ gates by order status.
            # Do not echo ecommerce JSON in the API response (avoids early client fire).

            if payment_type == Order.PAYMENT_LIQPAY:
                return Response(
                    {
                        "success": True,
                        "redirect_url": "/payment/",
                        "order_number": order_number,
                    },
                    status=status.HTTP_201_CREATED,
                )

            return Response(
                {
                    "success": True,
                    "message": "Замовлення успішно оформлено!",
                    "order_number": order_number,
                },
                status=status.HTTP_201_CREATED,
            )
        except ValueError as e:
            return Response(
                {"message": str(e), "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as e:
            error_message = "".join(e.messages) if hasattr(e, "messages") else str(e)
            return Response(
                {"message": error_message, "error": error_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {
                    "message": f"Помилка при створенні замовлення: {str(e)}",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
