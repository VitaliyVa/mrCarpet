from rest_framework import generics
from rest_framework import mixins
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework import permissions
from rest_framework.decorators import api_view
from rest_framework import status
from rest_framework.response import Response
from django_filters import rest_framework as rest_filters
from django.http import JsonResponse

from cart.utils import get_cart
from .permissions import IsAdminEdit, IsFavouriteOwner
from .serializers import (
    ProductSerializer,
    FavouriteSerializer,
    FavouriteProductsSerializer,
    ProductReviewSerializer,
)
from ..models import Product, Favourite, FavouriteProducts, ProductReview, PromoCode, ProductAttribute
from ..utils import get_favourite
from .filters import ProductFilter


class FavouriteProductPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if obj.favourite.user != request.user:
            return False
        print(obj.favourite)
        return True


# class ProductApiView(generics.ListAPIView):
#     serializer_class = ProductSerializer
#     queryset = Product.objects.all()


class FavouriteApiView(generics.ListAPIView):
    serializer_class = FavouriteSerializer
    queryset = Favourite.objects.all()

    # def get(self, request, *args, **kwargs):
    #     return Response(FavouriteSerializer(Favourite.objects.all(), many=True).data)


class FavouriteProductView(mixins.ListModelMixin, generics.GenericAPIView):
    serializer_class = FavouriteProductsSerializer
    queryset = FavouriteProducts.objects.all()
    lookup_field = "pk"
    permission_classes = [FavouriteProductPermission]

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    # @permission_classes([FavouriteProductPermission])
    def post(self, request, *args, **kwargs):
        serializer = FavouriteProductsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        print(serializer.validated_data)
        favorite_product = FavouriteProducts.objects.filter(
            **serializer.validated_data
        ).first()
        if favorite_product:
            return JsonResponse({"bad": "request"})
        favourite = serializer.validated_data["favourite"]
        if favourite.user == request.user:
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)

    # @permission_classes([FavouriteProductPermission])
    # def delete(self, request, *args, **kwargs):
    #     return self.destroy(request, *args, **kwargs)

    # @permission_classes([permissions.IsAuthenticated])
    def delete(self, request, *args, **kwargs):
        serializer = FavouriteProductsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # data = {
        #     'favourite': request.data['favourite'],
        #     'product': request.data['product']
        # }
        favorite_product = FavouriteProducts.objects.filter(
            **serializer.validated_data
        ).first()
        if favorite_product:
            favorite_product.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class ProductReviewViewSet(ModelViewSet):
    queryset = ProductReview.objects.all()
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAdminEdit]


class FavouriteProductViewSet(ModelViewSet):
    # queryset = FavouriteProducts.objects.all()
    serializer_class = FavouriteProductsSerializer
    permission_classes = [IsFavouriteOwner]
    lookup_field = "product__product_attr__id"

    def get_queryset(self):
        favourite = get_favourite(self.request)
        return FavouriteProducts.objects.filter(favourite=favourite)

    def create(self, request, *args, **kwargs):
        try:
            request.data._mutable = True
        except:
            "it is not a drf request"
        request.data["favourite"] = get_favourite(request).id
        try:
            product = ProductAttribute.objects.get(id=int(request.data["product"])).product.id
            request.data["product"] = str(product)
        except:
            return Response(
                {"message": "Помилка"},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fav_product = FavouriteProducts.objects.get(**serializer.validated_data)
            return Response(
                {"message": "Даний товар вже у вашому списку."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except FavouriteProducts.DoesNotExist:
            fav_product = FavouriteProducts.objects.create(**serializer.validated_data)
            return Response(
                {"favourite": FavouriteSerializer(get_favourite(request)).data, "message": "Товар додано!"}, status=status.HTTP_201_CREATED
            )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        print("ok")

        return Response(
            FavouriteSerializer(get_favourite(request)).data,
            status=status.HTTP_200_OK
        )


class ProductViewSet(mixins.ListModelMixin, GenericViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    # filter_backends = [filters.OrderingFilter, rest_filters.DjangoFilterBackend]
    filter_backends = [rest_filters.DjangoFilterBackend]
    filterset_class = ProductFilter
    # ordering_fields = ["title", "product_attr__price"]
    # ordering = ["-id"]
    # ordering_param = "sort"


@api_view(["POST"])
def apply_promocode(request):
    code = request.data["code"]
    cart = get_cart(request)
    promocode = PromoCode.objects.filter(code=code).first()
    if not promocode or not promocode.is_active:
        return Response(
            {"message": "Промокод не дійсний"}, status=status.HTTP_400_BAD_REQUEST
        )
    cart.promocode = promocode
    cart.save()
    return Response({"message": "Промокод додано"}, status=status.HTTP_200_OK)
