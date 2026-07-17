from django.core.validators import RegexValidator
from django.db import models
from django.contrib.auth.models import AbstractUser

from .managers import CustomUserManager


# Create your models here.
class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    phone_regex = RegexValidator(
        regex=r"^\+?1?\d{9,15}$",
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.",
    )
    phone_number = models.CharField(
        validators=[phone_regex], max_length=17, blank=True, null=True, unique=True
    )
    # Збережена адреса НП для автозаповнення в чекауті
    delivery_city = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Місто доставки"
    )
    delivery_settlement_ref = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Ref міста НП"
    )
    delivery_warehouse = models.CharField(
        max_length=512, blank=True, default="", verbose_name="Відділення НП"
    )
    delivery_warehouse_ref = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Ref відділення НП"
    )
    delivery_warehouse_id = models.CharField(
        max_length=64, blank=True, default="", verbose_name="ID відділення НП"
    )

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["password"]

    # objects = CustomUserManager()

    def __str__(self):
        return self.email