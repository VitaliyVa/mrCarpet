import logging
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status
from rest_framework.response import Response

from catalog.models import ProductAttribute, ProductWidth
from ..models import CartProduct, Cart
from ..utils import get_cart
from .serializers import CartProductSerializer, CartSerializer

logger = logging.getLogger(__name__)


class CartProductViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = CartProduct.objects.all()
    serializer_class = CartProductSerializer
    lookup_field = "id"
    
    def list(self, request, *args, **kwargs):
        """Повертає товари з поточної корзини користувача"""
        cart = get_cart(request)
        cart_products = cart.cart_products.all()
        serializer = self.get_serializer(cart_products, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        # Мутуємо копію, а не request.data (QueryDict immutable для form-даних)
        data = request.data.copy()
        cart = get_cart(request)
        logger.debug("Cart create: request data=%s", dict(data))
        data["cart"] = cart.id
        quantity = int(data["quantity"])
        data["product_attr"] = data["product"]

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        length = serializer.validated_data.pop("length", None)
        width = serializer.validated_data.pop("width", None)

        logger.debug("Cart create: quantity=%s length=%s width=%s", quantity, length, width)

        if (not length and width) or (length and not width):
            return Response(
                {"error": "Виберіть довжину і ширину"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        product = ProductAttribute.objects.filter(
            id=data["product_attr"]
        ).first()

        if not product:
            logger.warning("Cart create: ProductAttribute %s not found", data.get("product_attr"))
            return Response(
                {"error": "Товар не знайдено"}, status=status.HTTP_404_NOT_FOUND
            )

        logger.debug(
            "Cart create: product id=%s quantity=%s custom=%s",
            product.id, product.quantity, product.custom_attribute,
        )

        # Виправлена перевірка діапазону довжини
        if length and product.custom_attribute:
            if Decimal(length) < product.min_len or Decimal(length) > product.max_len:
                logger.debug(
                    "Cart create: length %s out of range [%s, %s]",
                    length, product.min_len, product.max_len,
                )
                return Response(
                    {"error": f"Некоректний розмір. Довжина повинна бути від {product.min_len} до {product.max_len}м"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        unique_data_fields = {
            "cart": serializer.validated_data["cart"],
            "product_attr": serializer.validated_data["product_attr"],
        }
        cart_product = CartProduct.objects.filter(**unique_data_fields).first()

        logger.debug(
            "Cart create: existing cart_product=%s quantity=%s",
            cart_product, cart_product.quantity if cart_product else 0,
        )

        # Для кастомних товарів не перевіряємо quantity, оскільки вони виробляються на замовлення
        is_custom = product.custom_attribute

        if cart_product:
            # Якщо товар вже є в кошику
            if is_custom or cart_product.able_add_to_cart(quantity=quantity + cart_product.quantity):
                cart_product.quantity += quantity
                # Якщо це кастомний товар з параметрами, перераховуємо total_price
                if is_custom and length and width and cart_product.total_price:
                    # Розраховуємо ціну за одиницю і множимо на нову кількість
                    price_per_unit = float(cart_product.total_price) / (cart_product.quantity - quantity)
                    cart_product.total_price = Decimal(price_per_unit * cart_product.quantity)
                # Оновлюємо length якщо передано
                if is_custom and length:
                    cart_product.length = Decimal(length)
                cart_product.save()
            else:
                logger.debug(
                    "Cart create: stock check failed, requested %s + in-cart %s > available %s",
                    quantity, cart_product.quantity, product.quantity,
                )
                return Response(
                    {"message": "Товар закінчився."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif is_custom or quantity <= product.quantity:
            cart_product = CartProduct.objects.create(**serializer.validated_data)
            if length and width and product.custom_attribute:
                cart_product.total_price = (
                    Decimal(width.width) * Decimal(length) * product.custom_price
                )
                cart_product.length = Decimal(length)
                cart_product.save()
            elif product.custom_attribute and (not length or not width):
                cart_product.total_price = product.get_total_price()
                if length:
                    cart_product.length = Decimal(length)
                cart_product.save()
        else:
            # Цей блок тепер не повинен виконуватися, але залишаємо для безпеки
            logger.debug(
                "Cart create: quantity check failed, requested %s > available %s (custom=%s)",
                quantity, product.quantity, is_custom,
            )
            return Response(
                {"message": "Товар закінчився."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        # Мутуємо копію, а не request.data — той самий флоу, що UpdateModelMixin
        data = request.data.copy()
        quantity = data.get("quantity", None)
        increment = data.get("increment", None)
        logger.debug("Cart update: id=%s quantity=%s increment=%s", instance.id, quantity, increment)
        if (quantity and increment) is None:
            return Response(
                {"message": "Wrong request"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if quantity > 0 and increment is True:
            data["quantity"] = instance.quantity + quantity
        elif quantity > 0 and increment is False:
            if instance.quantity == 1:
                data["quantity"] = 1
            else:
                data["quantity"] = instance.quantity - quantity

        # Оновлюємо total_price для кастомних продуктів
        if instance.product_attr.custom_attribute and instance.total_price is not None:
            new_quantity = data.get("quantity", instance.quantity)
            # Розраховуємо ціну за одиницю
            price_per_unit = instance.total_price / instance.quantity
            data["total_price"] = price_per_unit * new_quantity

        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            CartSerializer(get_cart(request), context={"request": request}).data,
            status=status.HTTP_200_OK
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()

        return Response(
            CartSerializer(get_cart(request), context={"request": request}).data,
            status=status.HTTP_200_OK
        )


# class CartViewSet(ModelViewSet):
#     queryset = Cart.objects.all()
#     serializer_class = CartSerializer
