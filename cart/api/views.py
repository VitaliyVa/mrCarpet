from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status
from rest_framework.response import Response

from catalog.models import ProductAttribute, ProductWidth
from ..models import CartProduct, Cart
from ..utils import get_cart
from .serializers import CartProductSerializer, CartSerializer


class CartProductViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    queryset = CartProduct.objects.all()
    serializer_class = CartProductSerializer
    lookup_field = "id"

    def create(self, request, *args, **kwargs):
        try:
            request.data._mutable = True
        except:
            "it is not a drf request"
        cart = get_cart(request)
        print(request.data)
        print(self.get_serializer())
        request.data["cart"] = cart.id
        quantity = int(request.data["quantity"])
        request.data["product_attr"] = request.data["product"]
        # print(type(length))
        # if (not length and width) or (length and not width):
        #     return Response(
        #         {"error": "Виберіть довжину і ширину"},
        #         status=status.HTTP_400_BAD_REQUEST,
        #     )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        length = serializer.validated_data.pop("length", None)
        width = serializer.validated_data.pop("width", None)
        if (not length and width) or (length and not width):
            return Response(
                {"error": "Виберіть довжину і ширину"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product = ProductAttribute.objects.filter(
            id=request.data["product_attr"]
        ).first()
        if length and product.min_len > Decimal(length) > product.max_len:
            return Response(
                {"error": "Некоректний розмір"}, status=status.HTTP_400_BAD_REQUEST
            )
        unique_data_fields = {
            "cart": serializer.validated_data["cart"],
            "product_attr": serializer.validated_data["product_attr"],
        }
        cart_product = CartProduct.objects.filter(**unique_data_fields).first()
        if cart_product and cart_product.able_add_to_cart(
            quantity=quantity + cart_product.quantity
        ):
            cart_product.quantity += quantity
            cart_product.save()
        elif not cart_product and quantity <= product.quantity:
            cart_product = CartProduct.objects.create(**serializer.validated_data)
            if length and width and product.custom_attribute:
                print("yes")
                cart_product.total_price = (
                    Decimal(width.width) * Decimal(length) * product.custom_price
                )
                print(cart_product.total_price)
                cart_product.save()
            elif product.custom_attribute and (not length or not width):
                # Якщо продукт кастомний, але розміри не вказані, використовуємо звичайну ціну
                print(f"Custom product without dimensions, using base price: {product.get_total_price()}")
                cart_product.total_price = product.get_total_price()
                cart_product.save()
        else:
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
        quantity = request.data.get("quantity", None)
        increment = request.data.get("increment", None)
        print(increment)
        if (quantity and increment) is None:
            return Response(
                {"message": "Wrong request"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if quantity > 0 and increment is True:
            request.data["quantity"] = instance.quantity + quantity
        elif quantity > 0 and increment is False:
            if instance.quantity == 1:
                request.data["quantity"] = 1
            else:
                request.data["quantity"] = instance.quantity - quantity
        
        # Оновлюємо total_price для кастомних продуктів
        if instance.product_attr.custom_attribute and instance.total_price is not None:
            new_quantity = request.data.get("quantity", instance.quantity)
            # Розраховуємо ціну за одиницю
            price_per_unit = instance.total_price / instance.quantity
            request.data["total_price"] = price_per_unit * new_quantity
        
        super().update(request, *args, **kwargs)
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
