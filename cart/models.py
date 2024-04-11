from django.db import models
from s_content.models import AbstractCreatedUpdated
from users.models import CustomUser
from .price import cart_total_price

# Create your models here.
class Cart(AbstractCreatedUpdated):
    user = models.ForeignKey(
        verbose_name='Cart owner',
        to=CustomUser,
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
    promocode = models.ForeignKey(
        verbose_name="Промокод",
        to="catalog.PromoCode",
        on_delete=models.SET_NULL,
        related_name="carts",
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"{self.user.email}'s cart" if self.user else "Unknown cart"

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзини"

    def get_total_price(self):
        return cart_total_price(self)

    def get_cart_product_total_quantity(self):
        return self.cart_products.all().aggregate(q=models.Sum("quantity"))["q"] or 0


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
    total_price = models.DecimalField(
        verbose_name="Загальна ціна",
        help_text="Тільки для кастомних варіацій",
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.product_attr.product.title
    
    def cart_product_total_price(self):
        product_price = self.product_attr.get_total_price()
        if self.product_attr.custom_attribute:
            product_price = float(self.total_price)
        price = product_price * self.quantity
        if price % 1 == 0:
            return int(price)
        return price

    def able_add_to_cart(self, quantity: int) -> bool:
        return quantity <= self.product_attr.quantity