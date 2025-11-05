from django.db import models

from s_content.models import AbstractCreatedUpdated


# Create your models here.
class ContactRequest(AbstractCreatedUpdated):
    name = models.CharField(max_length=115, verbose_name="Ім'я")
    email = models.EmailField(verbose_name="Пошта")
    text = models.TextField(verbose_name="Коментар")
    created = models.DateTimeField(
        verbose_name="Дата створення",
        auto_now_add=True,
        null=True,
        blank=True
    )
    is_processed = models.BooleanField(
        verbose_name="Оброблено",
        default=False
    )

    class Meta:
        verbose_name = "Контактна форма"
        verbose_name_plural = "Контактні форми"

    def __str__(self):
        return f"Запитання від {self.name}"


class Subscription(models.Model):
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.email

    class Meta:
        verbose_name = "Підписаний користувач"
        verbose_name_plural = "Підписані користувачі"


class SMTPSettings(models.Model):
    port = models.IntegerField(verbose_name="Порт")
    host = models.CharField(verbose_name="Хост", max_length=255)
    server_email = models.EmailField(verbose_name="Email сервера")
    email_host_password = models.CharField(verbose_name="Пароль", max_length=255)
    username = models.CharField(verbose_name="Логін", max_length=255, null=True, blank=True)
    use_tls = models.BooleanField(verbose_name="Використовувати TLS", default=True)
    use_ssl = models.BooleanField(verbose_name="Використовувати SSL", default=False)

    def __str__(self):
        return "Налаштування SMTP"
    
    class Meta:
        verbose_name = "Налаштування SMTP"
        verbose_name_plural = "Налаштування SMTP"

    def save(self, *args, **kwargs):
        if not self.pk and SMTPSettings.objects.exists():
            return
        return super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    