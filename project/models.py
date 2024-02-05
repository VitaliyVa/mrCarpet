from django.db import models

from s_content.models import AbstractCreatedUpdated


# Create your models here.
class ContactRequest(AbstractCreatedUpdated):
    name = models.CharField(max_length=115, verbose_name="Ім'я")
    email = models.EmailField(verbose_name="Пошта")
    text = models.TextField(verbose_name="Коментар")

    class Meta:
        verbose_name = "Контактна форма"
        verbose_name_plural = "Контактні форми"

    def __str__(self):
        return f"Запитання від {self.name}"
