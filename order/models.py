import random

from django.db import models

from s_content.models import AbstractCreatedUpdated


class Order(AbstractCreatedUpdated):
    STATUS_NEW = "new"
    STATUS_AWAITING_PAYMENT = "awaiting_payment"
    STATUS_PAID = "paid"
    STATUS_SHIPPED = "shipped"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_NEW, "Нове"),
        (STATUS_AWAITING_PAYMENT, "Очікує оплати"),
        (STATUS_PAID, "Оплачено, комплектується"),
        (STATUS_SHIPPED, "Відправлено"),
        (STATUS_COMPLETED, "Виконано"),
        (STATUS_CANCELLED, "Скасовано"),
    )

    PAYMENT_CASH = "cash"
    PAYMENT_LIQPAY = "liqpay"
    PAYMENT_CHOICES = (
        (PAYMENT_CASH, "Оплата при отриманні"),
        (PAYMENT_LIQPAY, "Онлайн оплата (LiqPay)"),
    )

    order_number = models.BigIntegerField(
        verbose_name="Номер замовлення",
        blank=True,
        null=True,
        editable=False,
        db_index=True,
    )
    status = models.CharField(
        verbose_name="Статус замовлення",
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
    )
    name = models.CharField(
        verbose_name="Ім'я",
        max_length=512,
    )
    surname = models.CharField(
        verbose_name="Прізвище",
        max_length=512,
    )
    email = models.EmailField(
        verbose_name="Email",
        max_length=254,
        blank=True,
        default="",
    )
    phone = models.CharField(
        verbose_name="Телефон",
        max_length=512,
        blank=True,
        null=True,
    )
    city = models.CharField(
        verbose_name="Місто",
        max_length=255,
        blank=True,
        default="",
        db_index=True,
    )
    address = models.CharField(
        verbose_name="Відділення НП",
        max_length=512,
        blank=True,
        null=True,
        help_text="Назва відділення / поштомату Нової Пошти",
    )
    message = models.CharField(
        verbose_name="Повідомлення",
        max_length=1024,
        blank=True,
        null=True,
    )
    total_price = models.FloatField(
        verbose_name="Сума",
        blank=True,
        null=True,
        db_index=True,
    )
    payment_type = models.CharField(
        verbose_name="Спосіб оплати",
        max_length=128,
        choices=PAYMENT_CHOICES,
        blank=False,
        null=False,
    )
    promocode = models.ForeignKey(
        verbose_name="Промокод",
        to="catalog.PromoCode",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="orders",
    )
    promocode_code = models.CharField(
        verbose_name="Промокод (код)",
        max_length=115,
        blank=True,
        default="",
        help_text="Знімок коду на момент замовлення (навіть якщо промокод видалять).",
    )
    promocode_discount = models.PositiveIntegerField(
        verbose_name="Промокод (знижка %)",
        blank=True,
        null=True,
        help_text="Знімок знижки % на момент замовлення.",
    )
    free_shipping = models.BooleanField(
        verbose_name="Безкоштовна доставка",
        default=False,
        db_index=True,
        help_text="Доставка за рахунок магазину (поріг на момент оформлення).",
    )
    free_shipping_threshold = models.PositiveIntegerField(
        verbose_name="Поріг безкоштовної доставки (грн)",
        null=True,
        blank=True,
        help_text="Який поріг діяв, коли замовлення отримало безкоштовну доставку.",
    )

    class Meta:
        verbose_name = "Замовлення"
        verbose_name_plural = "Замовлення"
        ordering = ("-created",)

    def __str__(self):
        number = self.order_number or self.pk or "?"
        customer = f"{self.name} {self.surname}".strip() or "—"
        return f"№{number} — {customer}"

    def can_order(self) -> bool:
        for cart_product in self.cart.cart_products.all():
            if cart_product.product.quantity < cart_product.quantity:
                return False
        return True

    def generate_order_number(self):
        return random.randint(1000000000000, 9999999999999)

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        return super().save(*args, **kwargs)

    @property
    def promocode_label(self) -> str:
        """Текст для адмінки / Telegram / листів."""
        code = (self.promocode_code or "").strip()
        if not code and self.promocode_id:
            code = self.promocode.code
        if not code:
            return ""
        discount = self.promocode_discount
        if discount is None and self.promocode_id:
            discount = self.promocode.discount
        if discount is not None:
            return f"{code} (−{discount}%)"
        return code


class PromoCodeRedemption(AbstractCreatedUpdated):
    """Факт використання промокоду в замовленні (лічильник лімітів)."""

    promocode = models.ForeignKey(
        verbose_name="Промокод",
        to="catalog.PromoCode",
        on_delete=models.CASCADE,
        related_name="redemptions",
    )
    order = models.OneToOneField(
        verbose_name="Замовлення",
        to=Order,
        on_delete=models.CASCADE,
        related_name="promo_redemption",
    )
    user = models.ForeignKey(
        verbose_name="Користувач",
        to="users.CustomUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="promo_redemptions",
    )
    email = models.EmailField(
        verbose_name="Email",
        max_length=254,
        blank=True,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Використання промокоду"
        verbose_name_plural = "Використання промокодів"
        indexes = [
            models.Index(fields=["promocode", "email"]),
        ]

    def __str__(self):
        return f"{self.promocode_id} → order {self.order_id}"
