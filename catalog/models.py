from django.db import models
from django.contrib.auth.models import User

from s_content.models import AbstractCreatedUpdated, AbstractMetaTags, AbstractTitleSlug

# Create your models here.
class Product(AbstractCreatedUpdated, AbstractMetaTags, AbstractTitleSlug):
    description = models.TextField(
        verbose_name='Description',
        blank=True,
        null=True
    )
    # prices = models.ManyToManyField(
    #     verbose_name='Ціни',
    #     blank=True,
    #     null=True,
    #     to='catalog.ProductSizePrice',
    #     related_name='product_prices'
    # )
    image = models.ImageField(
        verbose_name='Зображення',
        max_length=512,
        blank=True,
        upload_to='products'
    )
    categories = models.ManyToManyField(
        verbose_name='Категорії',
        blank=True,
        to='catalog.ProductCategory',
        related_name='products'
    )
    quantity = models.PositiveSmallIntegerField(
        verbose_name='Кількість'
    )
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
        verbose_name = 'Товар'
        verbose_name_plural = 'Товари'

    def __str__(self):
        return self.title


class ProductCategory(AbstractTitleSlug):
    image = models.ImageField(
        verbose_name='Зображення',
        max_length=512,
        blank=True,
        upload_to='categories'
    )

    class Meta:
        verbose_name = 'Категорія'
        verbose_name_plural = 'Категорії'

    def __str__(self):
        return self.title


class Size(models.Model):
    title = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = 'Розмір'
        verbose_name_plural = 'Розміри'

    def __str__(self):
        return self.title


class ProductAttribute(models.Model):
    product = models.ForeignKey(
        verbose_name='Товар',
        to='catalog.Product',
        on_delete=models.CASCADE,
        related_name='product_attr',
        blank=True,
        null=True
    )
    size = models.ForeignKey(
        verbose_name='Розмір',
        to='catalog.Size',
        on_delete=models.CASCADE,
        related_name='product_attr',
        blank=True,
        null=True
    )
    discount = models.IntegerField(
        verbose_name="Знижка",
        blank=True,
        null=True,
        help_text="Знижка у відсотках"
    )
    price = models.IntegerField(verbose_name='Ціна', blank=True, null=True)
    
    class Meta:
        verbose_name = 'Варіація'
        verbose_name_plural = 'Варіації'

    def __str__(self):
        return self.product.title

    def get_total_price(self):
        if self.discount:
            discount = self.discount / 100
            total_price = self.price - (self.price * discount)
            return total_price
        else:
            return self.price

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
        verbose_name='Назва',
        max_length=128,
        blank=True,
        null=True
    )

    class Meta:
        verbose_name = 'Характеристика'
        verbose_name_plural = 'Характеристики'

    def __str__(self):
        return self.title


class SpecificationValue(models.Model):
    title = models.CharField(
        verbose_name='Назва',
        max_length=128,
        blank=True,
        null=True
    )

    class Meta:
        verbose_name = 'Значення характеристики'
        verbose_name_plural = 'Значення характеристик'

    def __str__(self):
        return self.title


class ProductSpecification(models.Model):
    product = models.ForeignKey(
        verbose_name='Товар',
        to='catalog.Product',
        on_delete=models.CASCADE,
        related_name='product_specs',
        blank=True,
        null=True
    )
    specification = models.ForeignKey(
        verbose_name='Характеристика',
        to='catalog.Specification',
        on_delete=models.CASCADE,
        related_name='product_specs',
        blank=True,
        null=True
    )
    spec_value = models.ForeignKey(
        verbose_name='Значення характеристики',
        to='catalog.SpecificationValue',
        on_delete=models.CASCADE,
        related_name='product_specs',
        blank=True,
        null=True
    )

    class Meta:
        verbose_name = 'Характеристика товару'
        verbose_name_plural = 'Характеристики товару'

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
        verbose_name='Товар',
        blank=False,
        to='catalog.Product',
        related_name='fav_products',
        through='FavouriteProducts',
    )
    user = models.OneToOneField(
        verbose_name='Юзер',
        blank=False,
        to=User,
        on_delete=models.CASCADE,
        related_name='user'
    )

    class Meta:
        verbose_name = 'Улюблені'
        verbose_name_plural = 'Улюблені'

    def __str__(self):
        return f"{self.user.username}'s favourites"


class FavouriteProducts(models.Model):
    favourite = models.ForeignKey(Favourite, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    order = models.IntegerField(default=1)

    class Meta:
        ordering = ['-order']
        verbose_name = 'Улюблений товар'
        verbose_name_plural = 'Улюблені товари'

    def save(self, *args, **kwargs):
        self.order = FavouriteProducts.objects.first().order + 1
        return super().save(*args, **kwargs)