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
        url = reverse("index")
        return Response({"url": url}, status=status.HTTP_200_OK)

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
        user.save()
        return Response(
            {"message": "Дані успішно змінені!"},
            status=status.HTTP_200_OK
        )

