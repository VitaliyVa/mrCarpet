from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
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

    def get_total_price(self, *args, **kwargs):
        promo = kwargs.get("promo", None)
        price = cart_total_price(self)
        if promo:
            price = price - price * (promo / 100)
        return price

    def get_cart_product_total_quantity(self):
        return self.cart_products.all().aggregate(q=models.Sum("quantity"))["q"] or 0

    def apply_quantity(self):
        from django.db import connection
        from django.db.models import Sum, F
        connection.force_debug_cursor = True
        with transaction.atomic():
            out_of_stock_products = []
            
            # Спочатку агрегуємо всі кастомні товари за product_attr, щоб правильно відняти сумарну довжину
            from collections import defaultdict
            custom_products_by_attr = defaultdict(lambda: Decimal('0'))
            
            for cart_product in self.cart_products.all():
                # Збираємо сумарну довжину для кожного ProductAttribute
                if cart_product.product_attr.custom_attribute:
                    if cart_product.length:
                        custom_products_by_attr[cart_product.product_attr.id] += Decimal(cart_product.length) * cart_product.quantity
            
            # Тепер віднімаємо сумарну довжину для кожного ProductAttribute
            for product_attr_id, total_length_to_subtract in custom_products_by_attr.items():
                from catalog.models import ProductAttribute
                product_attr = ProductAttribute.objects.select_for_update().get(id=product_attr_id)
                if product_attr.max_len:
                    new_max_len = product_attr.max_len - total_length_to_subtract
                    # Переконуємося, що max_len не стане меншим за min_len
                    if new_max_len < product_attr.min_len:
                        product_attr.max_len = product_attr.min_len
                    else:
                        product_attr.max_len = new_max_len
                    product_attr.save()
                    print(f"Custom product (id={product_attr_id}): decreased max_len by {total_length_to_subtract}m, new max_len: {product_attr.max_len}")
            
            # Обробляємо звичайні товари та пропускаємо кастомні (вони вже оброблені вище)
            for cart_product in self.cart_products.all():
                # Пропускаємо кастомні товари (вони вже оброблені вище)
                if cart_product.product_attr.custom_attribute:
                    continue
                
                if cart_product.able_add_to_cart(cart_product.quantity):
                    cart_product.product_attr.quantity -= cart_product.quantity
                    cart_product.product_attr.save()
                else:
                    out_of_stock_products.append(cart_product.product_attr)
            if out_of_stock_products:
                print(out_of_stock_products)
                error_message = [
                    f'Доступна кількість товару {product_attr.product.title}: {product_attr.quantity}'
                    for product_attr in out_of_stock_products
                ]
                raise ValidationError("\n".join(error_message))
            print(len(connection.queries))
            self.save()


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
    length = models.DecimalField(
        verbose_name="Довжина",
        help_text="Довжина кастомного товару в метрах",
        max_digits=5,
        decimal_places=1,
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.product_attr.product.title
    
    def cart_product_total_price(self):
        # Для кастомних товарів використовуємо total_price якщо він встановлений
        if self.product_attr.custom_attribute:
            if self.total_price is not None:
                product_price = float(self.total_price)
            else:
                # Якщо total_price не встановлений, спробуємо отримати з product_attr
                product_price = self.product_attr.get_total_price()
                # Якщо і це None, повертаємо 0
                if product_price is None:
                    product_price = 0
        else:
            product_price = self.product_attr.get_total_price()
            # Для звичайних товарів якщо price None, повертаємо 0
            if product_price is None:
                product_price = 0
        
        price = product_price * self.quantity
        
        if price % 1 == 0:
            return int(price)
        return price

    def able_add_to_cart(self, quantity: int) -> bool:
        return quantity <= self.product_attr.quantity
    
    class Meta:
        verbose_name = "Товар в корзині"
        verbose_name_plural = "Товари в корзині"