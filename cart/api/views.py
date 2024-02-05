from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status
from rest_framework.response import Response

from catalog.models import ProductAttribute
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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = ProductAttribute.objects.filter(
            id=request.data["product_attr"]
        ).first()
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
        else:
            return Response(
                {"message": "Неможливо додати товар у корзину"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# class CartViewSet(ModelViewSet):
#     queryset = Cart.objects.all()
#     serializer_class = CartSerializer
