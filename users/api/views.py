from django.contrib.auth import authenticate, login
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    CustomUserSerializer,
    UserLoginSerializer,
    ProfileUpdateSerializer,
)
from ..models import CustomUser
from ..permissions import IsProfileOwner


def _link_newsletter(user):
    try:
        from project.newsletter import get_or_link_subscription_for_user

        get_or_link_subscription_for_user(user)
    except Exception:
        pass


class UserViewSet(ViewSet):
    @action(detail=False, methods=["post"])
    def register(self, request):
        serializer = CustomUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        first_name = serializer.validated_data["first_name"]
        last_name = serializer.validated_data["last_name"]
        try:
            user = CustomUser.objects.get(email=serializer.validated_data["email"])
            return Response(
                {"message": "User with this email already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CustomUser.DoesNotExist:
            user = CustomUser.objects.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
            )
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            _link_newsletter(user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def user_login(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        user = authenticate(email=email, password=password)
        if not user:
            return Response(
                {"message": "User with these credentials doesn't exist"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        _link_newsletter(user)
        url = reverse("index")
        return Response({"url": url}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["patch", "get"], permission_classes=[IsProfileOwner])
    def newsletter(self, request):
        from project.newsletter import set_newsletter_enabled
        from project.models import Subscription

        if request.method == "GET":
            email = (request.user.email or "").strip().lower()
            sub = (
                Subscription.objects.filter(email__iexact=email).first()
                if email
                else None
            )
            return Response(
                {
                    "enabled": bool(sub and sub.is_active),
                    "email": email,
                }
            )

        enabled = request.data.get("enabled")
        if enabled is None:
            return Response(
                {"message": "Передайте enabled: true|false"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        else:
            enabled = bool(enabled)

        try:
            sub = set_newsletter_enabled(request.user, enabled)
        except ValueError as exc:
            return Response(
                {"message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "enabled": sub.is_active,
                "email": sub.email,
                "message": (
                    "Підписку на розсилку увімкнено"
                    if sub.is_active
                    else "Підписку на розсилку вимкнено"
                ),
            }
        )

    @action(detail=False, methods=["patch"], permission_classes=[IsProfileOwner])
    def update_profile(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        email = serializer.validated_data.get("email", None)
        first_name = serializer.validated_data.get("first_name", None)
        last_name = serializer.validated_data.get("last_name", None)
        phone_number = serializer.validated_data.get("phone_number", None)
        password = serializer.validated_data.get("password", None)
        password2 = serializer.validated_data.get("password2", None)
        if password and password2:
            if password != password2:
                return Response(
                    {"error": "Паролі не співпадають"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.set_password(password)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        if (password and not password2) or (not password and password2):
            return Response(
                {"error": "Підтвердіть пароль"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if email:
            user.email = email
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if phone_number:
            user.phone_number = phone_number

        delivery_fields = (
            "delivery_city",
            "delivery_settlement_ref",
            "delivery_warehouse",
            "delivery_warehouse_ref",
            "delivery_warehouse_id",
        )
        for field in delivery_fields:
            if field in serializer.validated_data:
                setattr(user, field, serializer.validated_data.get(field) or "")

        user.save()
        return Response(
            {"message": "Дані успішно змінені!"},
            status=status.HTTP_200_OK
        )

