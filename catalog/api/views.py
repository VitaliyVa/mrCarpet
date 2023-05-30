from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics
from rest_framework import mixins
from rest_framework import permissions
from rest_framework.decorators import permission_classes
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from django.http import JsonResponse

from .serializers import ProductSerializer, FavouriteSerializer, FavouriteProductsSerializer
from ..models import Product, Favourite, FavouriteProducts


class FavouriteProductPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if obj.favourite.user != request.user:
            return False
        print(obj.favourite)
        return True


class ProductApiView(generics.ListAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()


class FavouriteApiView(APIView):
    # serializer_class = FavouriteSerializer
    # queryset = Favourite.objects.all()

    def get(self, request, *args, **kwargs):
        return Response(FavouriteSerializer(Favourite.objects.all(), many=True).data)


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
        favorite_product = FavouriteProducts.objects.filter(**serializer.validated_data).first()
        if favorite_product:
            return JsonResponse({'bad': 'request'})
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
        favorite_product = FavouriteProducts.objects.filter(**serializer.validated_data).first()
        if favorite_product:
            favorite_product.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)