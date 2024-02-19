from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins, status

from cart.utils import get_cart
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
        # data["total_price"] = cart.get_total_price()
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data["total_price"] = cart.get_total_price()
        order = Order.objects.create(**serializer.validated_data)
        cart.order = order
        # cart.ordered = True
        return Response(serializer.data, status=status.HTTP_201_CREATED)
