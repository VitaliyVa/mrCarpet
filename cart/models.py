from django.db import models
from django.contrib.auth.models import User
from s_content.models import AbstractCreatedUpdated
from .price import cart_total_price

# Create your models here.
class Cart(AbstractCreatedUpdated):
    user = models.ForeignKey(
        verbose_name='Cart owner',
        to=User,
        on_delete=models.SET_NULL,
        related_name='carts',
        blank=False,
        null=True
    )
    ordered = models.BooleanField(verbose_name="Замовлено", default=False)
    order = models.OneToOneField(
        verbose_name="Замовлення",
        to="order.Order",
        on_delete=models.SET_NULL,
        related_name="cart",
        blank=False,
        null=True,
    )

    def __str__(self):
        return f"{self.user.username}'s cart" if self.user else "Unknown cart"

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзини"

    def get_total_price(self):
        return cart_total_price(self)


class CartProduct(AbstractCreatedUpdated):
    cart = models.ForeignKey(
        verbose_name='Кошик',
        to='cart.Cart',
        on_delete=models.CASCADE,
        related_name='cart_products'
    )
    product_attr = models.ForeignKey(
        verbose_name='Товар',
        to='catalog.ProductAttribute',
        on_delete=models.CASCADE,
        related_name='cart_products'
    )
    quantity = models.PositiveSmallIntegerField(verbose_name='Кількість')

    def __str__(self):
        return self.product_attr.product.title