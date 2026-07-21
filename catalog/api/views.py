import logging

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
    ProductSaleSerializer,
    ProductSaleDetailSerializer,
    SaleSerializer,
    ProductCategorySerializer,
)
from ..models import Product, Favourite, FavouriteProducts, ProductReview, PromoCode, ProductAttribute, ProductSale, ProductCategory
from ..utils import get_favourite
from .filters import ProductFilter
from .pagination import CustomPagination

logger = logging.getLogger(__name__)


class FavouriteProductPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if obj.favourite.user != request.user:
            return False
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
    """
    Anyone may submit a review; nobody may publish one.

    IsAdminEdit only implements has_object_permission, which DRF does not call
    on create — so this endpoint has always accepted anonymous POSTs. That is
    fine for a review form and fatal for anything downstream of it, which is
    why moderation lives in the model default and the read side filters on it.
    """

    serializer_class = ProductReviewSerializer
    permission_classes = [IsAdminEdit]

    def get_queryset(self):
        # Reading is public, so only approved reviews are listed. Staff see
        # everything, which is what makes the admin useful.
        qs = ProductReview.objects.all()
        if self.request.user.is_staff:
            return qs
        return qs.filter(status=ProductReview.Status.APPROVED)

    def create(self, request, *args, **kwargs):
        # Мутуємо копію, а не request.data; далі — той самий флоу, що CreateModelMixin
        data = request.data.copy()
        try:
            product = ProductAttribute.objects.get(id=data["product"]).product.id
            data["product"] = str(product)
        except Exception as e:
            return Response(
                {"message": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Whatever the client sent for these, it does not get to decide them.
        data["status"] = ProductReview.Status.PENDING
        data["verified_purchase"] = False

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save(
            status=ProductReview.Status.PENDING,
            verified_purchase=False,
            ip_address=_client_ip(request),
        )

        _mark_verified_purchase(review)
        _notify_staff_new_review(review)

        # The submitter is told it was received, not shown the stored row:
        # echoing the record back would leak the moderation state and the
        # email of a review that is not public yet.
        return Response(
            {"ok": True, "message": "Дякуємо! Відгук з'явиться після перевірки."},
            status=status.HTTP_201_CREATED,
        )


class FavouriteProductViewSet(ModelViewSet):
    # queryset = FavouriteProducts.objects.all()
    serializer_class = FavouriteProductsSerializer
    permission_classes = [IsFavouriteOwner]
    lookup_field = "product__product_attr__id"

    def get_queryset(self):
        favourite = get_favourite(self.request)
        return FavouriteProducts.objects.filter(favourite=favourite)

    def create(self, request, *args, **kwargs):
        # Мутуємо копію, а не request.data (QueryDict immutable для form-даних)
        data = request.data.copy()
        data["favourite"] = get_favourite(request).id
        try:
            product = ProductAttribute.objects.get(id=int(data["product"])).product.id
            data["product"] = str(product)
        except Exception:
            return Response(
                {"message": "Помилка"},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = self.get_serializer(data=data)
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

        return Response(
            FavouriteSerializer(get_favourite(request)).data,
            status=status.HTTP_200_OK
        )


class ProductViewSet(mixins.ListModelMixin, GenericViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = CustomPagination
    # filter_backends = [filters.OrderingFilter, rest_filters.DjangoFilterBackend]
    filter_backends = [rest_filters.DjangoFilterBackend]
    filterset_class = ProductFilter
    # ordering_fields = ["title", "product_attr__price"]
    # ordering = ["-id"]
    # ordering_param = "sort"


class ProductCategoryViewSet(mixins.ListModelMixin, GenericViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    pagination_class = CustomPagination


@api_view(["POST"])
def apply_promocode(request):
    from catalog.promocode import PromoCodeError, resolve_and_validate

    code = request.data.get("code") or request.data.get("promocode")
    cart = get_cart(request)
    try:
        email = request.data.get("email") or ""
        if request.user.is_authenticated and not email:
            email = request.user.email or ""
        promocode = resolve_and_validate(
            code,
            user=request.user if request.user.is_authenticated else None,
            email=email,
            require_identity=False,
        )
    except PromoCodeError as exc:
        return Response(
            {"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST
        )
    promocode_price = round(
        cart.get_total_price() - cart.get_total_price() * (promocode.discount / 100),
        1,
    )
    if promocode_price % 1 == 0:
        promocode_price = int(promocode_price)
    return Response(
        {
            "promocode_id": promocode.id,
            "promocode_total_price": f"{promocode_price} грн",
            "message": "Промокод додано",
        },
        status=status.HTTP_200_OK,
    )
    
    
class SaleProductsViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    queryset = ProductSale.objects.all()
    # serializer_class = ProductSaleSerializer
    
    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductSaleDetailSerializer
        return SaleSerializer


def _client_ip(request) -> str | None:
    """Left-most X-Forwarded-For entry, since nginx sits in front."""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or None


def _mark_verified_purchase(review) -> None:
    """
    Flag the review when its email matches a real order for this product.

    Best effort and deliberately narrow: only a delivered or completed order
    counts, because "verified purchase" has to mean the person actually
    received the rug. A mismatch is not an error — plenty of honest reviewers
    order by phone or use a different address.
    """
    email = (review.email or "").strip().lower()
    if not email:
        return
    try:
        from order.models import Order

        matched = (
            Order.objects.filter(
                email__iexact=email,
                status__in=(Order.STATUS_SHIPPED, Order.STATUS_COMPLETED),
                cart__cart_products__product__product__id=review.product_id,
            )
            .exists()
        )
        if matched:
            type(review).objects.filter(pk=review.pk).update(verified_purchase=True)
    except Exception:
        logger.info("verified-purchase check skipped for review %s", review.pk)


def _notify_staff_new_review(review) -> None:
    """
    Tell the staff chat a review is waiting.

    Without this, moderation depends on someone remembering to open the admin,
    and a review sitting unapproved for a week is the same as no review at all
    — the customer sees nothing appear and does not write another.
    """
    try:
        from social.services.comment_notify import notify_staff_text

        stars = "★" * int(review.rating or 0)
        notify_staff_text(
            f"📝 Новий відгук на модерації\n"
            f"{review.product}\n"
            f"{stars} від {review.name}\n"
            f"{(review.content or '').strip()[:300]}\n\n"
            f"Схвалити: /admin/catalog/productreview/{review.pk}/change/"
        )
    except Exception:
        logger.info("review notification failed for %s", review.pk)
