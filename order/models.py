from django.db import models
from s_content.models import AbstractCreatedUpdated

# Create your models here.
class Order(AbstractCreatedUpdated):
    name = models.CharField(max_length=514)
    phone = models.CharField(max_length=514)