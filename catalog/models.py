from colorfield.fields import ColorField
from django.core.validators import MaxValueValidator
from django.db import models
from django.urls import reverse
import decimal

from django.utils import timezone

from cart.models import CartProduct
from s_content.models import AbstractCreatedUpdated, AbstractMetaTags, AbstractTitleSlug
from users.models import CustomUser


# Create your models here.
class Product(AbstractCreatedUpdated, AbstractMetaTags, AbstractTitleSlug):
    description = models.TextField(verbose_name="Description", blank=True, null=True)
    # prices = models.ManyToManyField(
    #     verbose_name='Ціни',
    #     blank=True,
    #     null=True,
    #     to='catalog.ProductSizePrice',
    #     related_name='product_prices'
    # )
    image = models.ImageField(
        verbose_name="Зображення", default="products/default.png", max_length=512, blank=True, upload_to="products"
    )
    categories = models.ManyToManyField(
        verbose_name="Категорії",
        blank=True,
        to="catalog.ProductCategory",
        related_name="products",
    )
    is_new = models.BooleanField(verbose_name="Новинка", default=True)
    colors = models.ManyToManyField(
        verbose_name="Кольори",
        blank=True,
        to="catalog.ProductColor",
    )
    has_discount = models.BooleanField(default=False)
    # discount = models.IntegerField(blank=True, null=True)
    # sizes = models.ManyToManyField(
    #     verbose_name='Розміри',
    #     blank=True,
    #     to='catalog.ProductSize',
    #     related_name='sizes'
    # )
    # favourites = models.ManyToManyField(
    #     verbose_name='Улюблені',
    #     blank=True,
    #     to=User,
    #     related_name='favourites'
    # )

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товари"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("product", args=(self.slug,))


class ProductImage(models.Model):
    product = models.ForeignKey(
        verbose_name="Продукт",
        to=Product,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image = models.ImageField(upload_to="products/additional", blank=False, null=False)
    alt = models.CharField(
        verbose_name="Image alt", max_length=500, blank=True, null=True
    )

    class Meta:
        verbose_name = "Зображення продукта"
        verbose_name_plural = "Зображення продуктів"

    def __str__(self):
        return f"{self.product.title}: {self.image.url}"


class ProductCategory(AbstractTitleSlug):
    image = models.ImageField(
        verbose_name="Зображення", max_length=512, blank=True, upload_to="categories"
    )

    class Meta:
        verbose_name = "Категорія"
        verbose_name_plural = "Категорії"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("categorie", kwargs={"slug": self.slug})


class Size(models.Model):
    title = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "Розмір"
        verbose_name_plural = "Розміри"

    def __str__(self):
        return self.title


class ProductColor(AbstractTitleSlug):
    color = ColorField(verbose_name="Колір", blank=False, unique=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Колір"
        verbose_name_plural = "Кольори"


class ProductWidth(models.Model):
    width = models.DecimalField(
        verbose_name="Ширина продукта",
        max_digits=4,
        decimal_places=1,
        blank=False,
        null=False,
    )

    class Meta:
        verbose_name = "Ширина продукта"
        verbose_name_plural = "Ширина продукта"

    def __str__(self):
        return str(self.width)


class ProductAttribute(models.Model):
    product = models.ForeignKey(
        verbose_name="Товар",
        to="catalog.Product",
        on_delete=models.CASCADE,
        related_name="product_attr",
        blank=True,
        null=True,
    )
    size = models.ForeignKey(
        verbose_name="Розмір",
        to="catalog.Size",
        on_delete=models.CASCADE,
        related_name="product_attr",
        blank=True,
        null=True,
    )
    discount = models.IntegerField(
        verbose_name="Знижка",
        blank=True,
        null=True,
        help_text="Знижка у відсотках",
        validators=[MaxValueValidator(100)],
    )
    price = models.IntegerField(verbose_name="Ціна", blank=True, null=True)
    quantity = models.PositiveSmallIntegerField(verbose_name="Кількість")
    # is_new = models.BooleanField(verbose_name="Новинка", default=True)
    custom_attribute = models.BooleanField(
        verbose_name="Кастомна варіація",
        help_text="Позначати тільки якщо це кастомний варіант!",
        default=False,
    )
    min_len = models.DecimalField(
        verbose_name="Мінімальна довжина",
        help_text="Позначати тільки якщо це кастомний варіант!",
        max_digits=4,
        decimal_places=1,
        blank=True,
        null=True,
    )
    max_len = models.DecimalField(
        verbose_name="Максимальна довжина",
        help_text="Позначати тільки якщо це кастомний варіант!",
        max_digits=4,
        decimal_places=1,
        blank=True,
        null=True,
    )
    width = models.ManyToManyField(
        verbose_name="Ширина",
        help_text="Позначати тільки якщо це кастомний варіант!",
        to=ProductWidth,
        related_name="widths",
        blank=True,
    )
    custom_price = models.DecimalField(
        verbose_name="Ціна за метр квадратний",
        help_text="Позначати тільки якщо це кастомний варіант!",
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Варіація"
        verbose_name_plural = "Варіації"

    def __str__(self):
        return f"{self.product.title} - {self.size.title if self.size else 'кастомна варіація'}"

    def get_total_price(self):
        if self.discount:
            discount = self.discount / 100
            total_price = self.price - (self.price * discount)
            if total_price % 1 == 0:
                return int(total_price)
            return float("{:.2f}".format(total_price))
        else:
            return self.price

    def set_discount(self):
        for prod in self.product.product_attr.all():
            if prod.discount:
                return True
            else:
                return False

    def save(self, *args, **kwargs):
        discount = super().save(*args, **kwargs)
        self.product.has_discount = self.set_discount()
        self.product.save()
        if self.custom_attribute:
            cart_products = CartProduct.objects.filter(product_attr=self)
            if cart_products:
                for cart_product in cart_products:
                    cart_product.delete()
        return discount


# class CustomProductAttribute(models.Model):
#     product = models.ForeignKey(
#         verbose_name="Товар",
#         to="catalog.Product",
#         on_delete=models.CASCADE,
#         related_name="custom_product_attr",
#         blank=True,
#         null=True,
#     )
#     min_len = models.DecimalField(
#         verbose_name="Мінімальна довжина",
#         max_digits=4,
#         decimal_places=1,
#         blank=False,
#         null=False,
#     )
#     max_len = models.DecimalField(
#         verbose_name="Максимальна довжина",
#         max_digits=4,
#         decimal_places=1,
#         blank=False,
#         null=False,
#     )
#     width = models.ManyToManyField(
#         verbose_name="Ширина",
#         to=ProductWidth,
#         related_name="widths",
#         blank=False,
#     )
#     discount = models.IntegerField(
#         verbose_name="Знижка",
#         blank=True,
#         null=True,
#         help_text="Знижка у відсотках",
#         validators=[MaxValueValidator(100)],
#     )
#     price = models.IntegerField(
#         verbose_name="Ціна за квадратний метр", blank=True, null=True
#     )
#     quantity = models.PositiveSmallIntegerField(verbose_name="Кількість")
#     is_new = models.BooleanField(verbose_name="Новинка", default=True)
#
#     class Meta:
#         verbose_name = "Кастомна варіація"
#         verbose_name_plural = "Кастомні варіації"
#
#     def __str__(self):
#         return f"{self.product.title} - кастомний розмір"
#
#     def get_total_price(self, width, length):
#         if self.discount:
#             discount = self.discount / 100
#             raw_price = width * length * self.price
#             total_price = raw_price - (raw_price * discount)
#             if total_price % 1 == 0:
#                 return int(total_price)
#             else:
#                 return "{:.2f}".format(total_price)
#         else:
#             return self.price
#
#     def set_discount(self):
#         for prod in self.product.product_attr.all():
#             if prod.discount:
#                 return True
#             else:
#                 return False
#
#     def save(self, *args, **kwargs):
#         discount = super().save(*args, **kwargs)
#         self.product.has_discount = self.set_discount()
#         self.product.save()
#         return discount


# class SizePrice(models.Model):
#     price = models.IntegerField(
#         verbose_name='Ціна',
#         blank=True,
#         null=True
#     )

#     class Meta:
#         verbose_name = 'Ціна розміру'
#         verbose_name_plural = 'Ціни розміру'

#     def __str__(self):
#         return f'{self.price} грн'


# class ProductSizePrice(models.Model):
#     product = models.ForeignKey(
#         verbose_name='Товар',
#         to='catalog.Product',
#         on_delete=models.CASCADE,
#         related_name='product_sizes',
#         blank=True,
#         null=True
#     )
#     size = models.ForeignKey(
#         verbose_name='Розмір',
#         to='catalog.Size',
#         on_delete=models.CASCADE,
#         related_name='product_sizes',
#         blank=True,
#         null=True
#     )
#     size_price = models.ForeignKey(
#         verbose_name='Ціна розміру',
#         to='catalog.SizePrice',
#         on_delete=models.CASCADE,
#         related_name='product_sizes',
#         blank=True,
#         null=True
#     )

#     class Meta:
#         verbose_name = 'Розмір товару'
#         verbose_name_plural = 'Розміри товару'

#     def __str__(self):
#         return f"{self.size}: {self.size_value}"


class Specification(models.Model):
    title = models.CharField(
        verbose_name="Назва", max_length=128, blank=True, null=True
    )

    class Meta:
        verbose_name = "Характеристика"
        verbose_name_plural = "Характеристики"

    def __str__(self):
        return self.title


class SpecificationValue(models.Model):
    title = models.CharField(
        verbose_name="Назва", max_length=128, blank=True, null=True
    )

    class Meta:
        verbose_name = "Значення характеристики"
        verbose_name_plural = "Значення характеристик"

    def __str__(self):
        return self.title


class ProductSpecification(models.Model):
    product = models.ForeignKey(
        verbose_name="Товар",
        to="catalog.Product",
        on_delete=models.CASCADE,
        related_name="product_specs",
        blank=True,
        null=True,
    )
    specification = models.ForeignKey(
        verbose_name="Характеристика",
        to="catalog.Specification",
        on_delete=models.CASCADE,
        related_name="product_specs",
        blank=True,
        null=True,
    )
    spec_value = models.ForeignKey(
        verbose_name="Значення характеристики",
        to="catalog.SpecificationValue",
        on_delete=models.CASCADE,
        related_name="product_specs",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Характеристика товару"
        verbose_name_plural = "Характеристики товару"

    def __str__(self):
        return f"{self.specification}: {self.spec_value}"


# class ProductSpecs(models.Model):
#     height = models.CharField(
#         verbose_name='Висота ворсу',
#         max_length=128,
#         blank=True,
#         null=True
#     )
#     main = models.CharField(
#         verbose_name='Ворсова основа',
#         max_length=128,
#         blank=True,
#         null=True
#     )
#     style = models.CharField(
#         verbose_name='Стилістика',
#         max_length=128,
#         blank=True,
#         null=True
#     )
#     components = models.CharField(
#         verbose_name='Склад',
#         max_length=128,
#         blank=True,
#         null=True
#     )
#     shape = models.CharField(
#         verbose_name='Форма',
#         max_length=128,
#         blank=True,
#         null=True
#     )
#     product = models.OneToOneField(
#         verbose_name='Продукт',
#         blank=False,
#         to='catalog.Product',
#         on_delete=models.CASCADE,
#         related_name='product_specs',
#     )

#     class Meta:
#         verbose_name = 'Специфікація'
#         verbose_name_plural = 'Специфікації'

#     def __str__(self):
#         return f"{self.product.title} - specs"


class Favourite(AbstractCreatedUpdated):
    product = models.ManyToManyField(
        verbose_name="Товар",
        blank=True,
        to="catalog.Product",
        related_name="fav_products",
        through="FavouriteProducts",
    )
    user = models.ForeignKey(
        verbose_name="Юзер",
        blank=False,
        null=True,
        to=CustomUser,
        on_delete=models.CASCADE,
        related_name="user",
    )

    class Meta:
        verbose_name = "Улюблені"
        verbose_name_plural = "Улюблені"

    def __str__(self):
        return (
            f"{self.user.first_name}'s favourites" if self.user else "unknown favourite"
        )


class FavouriteProducts(models.Model):
    favourite = models.ForeignKey(Favourite, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    order = models.IntegerField(default=1)

    class Meta:
        # ordering = ['order']
        verbose_name = "Улюблений товар"
        verbose_name_plural = "Улюблені товари"

    def save(self, *args, **kwargs):
        if FavouriteProducts.objects.first():
            self.order = FavouriteProducts.objects.first().order + 1
        else:
            self.order = 1
        return super().save(*args, **kwargs)


class ProductReview(AbstractCreatedUpdated):
    product = models.ForeignKey(
        verbose_name="Продукт",
        blank=False,
        null=False,
        to=Product,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    name = models.CharField(max_length=150, blank=False, null=False)
    content = models.TextField(blank=True, null=True)
    rating = models.IntegerField(
        validators=[MaxValueValidator(5)], blank=False, null=False
    )

    class Meta:
        verbose_name = "Відгук"
        verbose_name_plural = "Відгуки"

    def __str__(self):
        return f"{self.name}'s review"


class RelatedProduct(models.Model):
    related_to = models.ForeignKey(
        verbose_name="Відповідний товар",
        blank=False,
        null=False,
        to=Product,
        on_delete=models.CASCADE,
        related_name="related_products",
    )
    product = models.ForeignKey(
        verbose_name="Схожий товар",
        blank=False,
        null=False,
        to=Product,
        on_delete=models.CASCADE,
        related_name="related_to_products",
    )

    def __str__(self):
        return self.product.title


class ProductSale(AbstractCreatedUpdated):
    date_end = models.DateTimeField(verbose_name="Кінець розпродажу")
    products = models.ManyToManyField(
        verbose_name="Товари на акції",
        to=Product,
    )

    def __str__(self):
        return f"Акція до {self.date_end}"

    class Meta:
        verbose_name = "Акція"
        verbose_name_plural = "Акції"


class PromoCode(AbstractCreatedUpdated):
    code = models.CharField(
        verbose_name="Код",
        max_length=115,
        blank=False,
        null=False
    )
    end_time = models.DateTimeField(verbose_name="Дата закінчення")
    discount = models.PositiveIntegerField(
        verbose_name="Знижка",
        validators=[MaxValueValidator(100)],
        blank=False,
        null=False,
        default=None,
        help_text="У відсотках"
    )

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоди"

    def __str__(self):
        return self.code

    @property
    def is_active(self):
        if self.end_time < timezone.now():
            return False
        return True
