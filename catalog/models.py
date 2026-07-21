from pathlib import Path
import decimal

from colorfield.fields import ColorField
from django.core.validators import MaxValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum, Case, When, IntegerField
from django.urls import reverse

from django.utils import timezone

from cart.models import CartProduct
from s_content.models import AbstractCreatedUpdated, AbstractMetaTags, AbstractTitleSlug
from users.models import CustomUser


class ProductManager(models.Manager):
    def get_queryset(self):
        products = (
            super().get_queryset().annotate(
                total_quantity=Sum("product_attr__quantity"),
                has_attribute_with_quantity_gt_zero=Case(
                    When(total_quantity__gt=0, then=1),
                    When(total_quantity=0, then=2),
                    output_field=IntegerField(),
                )
            )
            .filter(has_attribute_with_quantity_gt_zero__gt=0)
            .order_by("has_attribute_with_quantity_gt_zero", "-created")
        )
        return products


class ProductAdminManager(models.Manager):
    """Менеджер для адмінки, який показує всі товари"""
    def get_queryset(self):
        return super().get_queryset().order_by("-created")


class ColorGroup(models.Model):
    """Обʼєднує кольорові варіанти одного килима (товари з різними назвами)."""
    name = models.CharField(verbose_name="Назва групи", max_length=255, blank=True)

    class Meta:
        verbose_name = "Кольорова група"
        verbose_name_plural = "Кольорові групи"

    def __str__(self):
        return self.name or f"Кольорова група #{self.pk}"


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
        verbose_name="Зображення", default="products/default.png", max_length=512, blank=True, upload_to="products",
        help_text="Основне фото для каталогу (можна в меншій якості). На детальній сторінці не показується."
    )
    hover_image = models.ImageField(
        verbose_name="Зображення при наведенні", max_length=512, blank=True, upload_to="products",
        help_text="Фото для каталогу при наведенні (можна в меншій якості). На детальній сторінці не показується."
    )
    categories = models.ManyToManyField(
        verbose_name="Категорії",
        blank=True,
        to="catalog.ProductCategory",
        related_name="products",
    )
    is_new = models.BooleanField(
        verbose_name="Новинка",
        default=True,
        help_text=(
            "Увімкнено за замовчуванням. Бейдж на сайті лише протягом N днів "
            "від дати створення (N у Налаштуваннях магазину, зараз 90). "
            "Зніми галочку, щоб сховати «Новинку» раніше."
        ),
    )
    colors = models.ManyToManyField(
        verbose_name="Кольори",
        blank=True,
        to="catalog.ProductColor",
    )
    active_color = models.ForeignKey(
        verbose_name="Активний колір",
        to="catalog.ProductColor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_products",
    )
    color_group = models.ForeignKey(
        verbose_name="Кольорова група",
        to="catalog.ColorGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="variants",
        help_text="Обʼєднує кольорові варіанти одного килима (з різними назвами). "
                  "Плитки кольорів на сторінці товару беруться з цієї групи.",
    )
    has_discount = models.BooleanField(default=False)

    AR_STATUS_NONE = "none"
    AR_STATUS_PENDING = "pending"
    AR_STATUS_READY = "ready"
    AR_STATUS_FAILED = "failed"
    AR_STATUS_CHOICES = (
        (AR_STATUS_NONE, "Немає"),
        (AR_STATUS_PENDING, "Генерується"),
        (AR_STATUS_READY, "Готово"),
        (AR_STATUS_FAILED, "Помилка"),
    )
    ar_texture = models.ImageField(
        verbose_name="AR-текстура",
        upload_to="ar/textures",
        blank=True,
        null=True,
        help_text="PNG з alpha для 3D/AR. Генерується з каталожного фото або завантажується вручну.",
    )
    ar_status = models.CharField(
        verbose_name="Статус AR",
        max_length=16,
        choices=AR_STATUS_CHOICES,
        default=AR_STATUS_NONE,
        db_index=True,
    )
    ar_error = models.TextField(verbose_name="Помилка AR", blank=True, default="")
    ar_updated_at = models.DateTimeField(
        verbose_name="AR оновлено",
        null=True,
        blank=True,
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
    objects = ProductManager()
    admin_objects = ProductAdminManager()

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товари"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Генеруємо slug з title + active_color (якщо є)
        # Це гарантує унікальність slug для товарів з однаковим title але різними кольорами
        from django.utils.text import slugify
        from unidecode import unidecode

        # Once only. This used to run on every save, so correcting a typo in a
        # product title changed its URL — killing the link Google had indexed,
        # the sitemap entry, and any link a customer had shared. A prettier
        # slug is not worth a dead URL. To re-slug deliberately, clear the
        # field and save.
        if (self.slug or "").strip():
            super().save(*args, **kwargs)
            return

        if self.title:
            # Базова частина slug з title
            base_slug = slugify(unidecode(self.title))
            
            # Додаємо active_color до slug якщо він є
            if self.active_color and self.active_color.title:
                color_slug = slugify(unidecode(self.active_color.title))
                base_slug = f"{base_slug}-{color_slug}"
            
            # Перевіряємо унікальність
            from s_utils.model_fields import check_s_availability
            self.slug = check_s_availability(self, base_slug)
        else:
            # Якщо title немає, використовуємо стандартну генерацію
            from s_utils.model_fields import generate_slug
            self.slug = generate_slug(self)
        
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("product", args=(self.slug,))

    def get_size_attrs(self):
        """Фіксовані розміри (без кастомної варіації), у порядку sort_order."""
        return self.product_attr.filter(custom_attribute=False)

    def get_default_size_attr(self):
        """
        Розмір за замовчуванням: перший у наявності.
        Якщо всі out of stock — перший у списку (щоб UI не ламався).
        """
        attrs = list(self.get_size_attrs())
        if not attrs:
            return self.product_attr.filter(custom_attribute=True).first()
        for attr in attrs:
            if attr.in_stock:
                return attr
        return attrs[0]

    @property
    def is_novelty(self) -> bool:
        """Бейдж «Новинка» на вітрині: is_new + вікно днів від created."""
        from project.novelty import product_is_novelty

        return product_is_novelty(self)


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
    sort_order = models.PositiveIntegerField(
        verbose_name="Порядок",
        default=0,
        help_text="Менше число — вище в слайдері на сторінці товару",
    )
    is_ai = models.BooleanField(
        verbose_name="Ілюстрація інтер'єру (ШІ)",
        default=False,
        help_text="Позначається автоматично для зображень, згенерованих у блоці «Генерація фото для сторінки товару»",
    )

    class Meta:
        verbose_name = "Зображення продукта"
        verbose_name_plural = "Зображення продуктів"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.title}: {self.image.url}"

    def save(self, *args, **kwargs):
        if self.sort_order == 0 and self.product_id:
            from django.db.models import Max

            current_max = (
                ProductImage.objects.filter(product_id=self.product_id)
                .exclude(pk=self.pk)
                .aggregate(m=Max("sort_order"))["m"]
            )
            self.sort_order = (current_max or 0) + 10
        super().save(*args, **kwargs)


class ProductCategory(AbstractMetaTags, AbstractTitleSlug):
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

    def save(self, *args, **kwargs):
        """Downscale category tiles to WebP (~560px @ q90) on upload."""
        from django.core.files.base import ContentFile

        from catalog.image_optimize import optimize_category_image

        if self.image:
            try:
                self.image.open("rb")
                data = self.image.read()
                self.image.close()
                # Skip already-small assets; re-encode heavy uploads
                if data and len(data) > 80_000:
                    optimized = optimize_category_image(data)
                    stem = Path(self.image.name).stem if self.image.name else "category"
                    self.image.save(
                        f"{stem}.webp",
                        ContentFile(optimized),
                        save=False,
                    )
            except Exception:
                pass
        super().save(*args, **kwargs)


class Size(models.Model):
    title = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "Розмір"
        verbose_name_plural = "Розміри"

    def __str__(self):
        return self.title


class ProductColor(AbstractTitleSlug):
    color = ColorField(verbose_name="Колір", blank=True, null=True)
    texture = models.ImageField(
        verbose_name="Текстура",
        upload_to="colors/textures",
        blank=True,
        null=True,
        help_text="Альтернатива кольору. Якщо завантажено текстуру, вона буде відображатися замість кольору."
    )

    def clean(self):
        from django.core.exceptions import ValidationError
        # Перевіряємо що є або color або texture (але не обидва)
        if not self.color and not self.texture:
            raise ValidationError({
                'color': "Необхідно вказати або колір, або завантажити текстуру.",
                'texture': "Необхідно вказати або колір, або завантажити текстуру."
            })
        if self.color and self.texture:
            raise ValidationError({
                'color': "Можна використати або колір, або текстуру, але не обидва одночасно.",
                'texture': "Можна використати або колір, або текстуру, але не обидва одночасно."
            })

    def save(self, *args, **kwargs):
        self.full_clean()  # Викликаємо clean() для валідації
        super().save(*args, **kwargs)

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
    sort_order = models.PositiveIntegerField(
        verbose_name="Порядок",
        default=0,
        help_text="Менше число — вище в списку. Ставиться автоматично при збереженні товару (за шириною).",
    )

    class Meta:
        verbose_name = "Варіація"
        verbose_name_plural = "Варіації"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.title} - {self.size.title if self.size else 'кастомна варіація'}"

    @property
    def in_stock(self) -> bool:
        """Чи можна купити цей розмір зараз."""
        if self.custom_attribute:
            if self.max_len is None:
                return False
            min_len = self.min_len or 0
            return self.max_len > min_len
        return (self.quantity or 0) > 0

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
    specification = models.ForeignKey(
        verbose_name="Характеристика",
        to="catalog.Specification",
        on_delete=models.CASCADE,
        related_name="values",
        blank=True,
        null=True,
        help_text="Характеристика до якої належить це значення"
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

    class Status(models.TextChoices):
        PENDING = "pending", "На модерації"
        APPROVED = "approved", "Опубліковано"
        REJECTED = "rejected", "Відхилено"

    #: Moderated by default, and that default is the whole point. The create
    #: endpoint is open to anonymous POSTs, and every review it accepted went
    #: straight into the aggregateRating that Google reads — a stranger could
    #: set the star rating of any product. Nothing reaches the page or the
    #: structured data until a human approves it.
    status = models.CharField(
        verbose_name="Статус",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    email = models.EmailField(
        verbose_name="Email",
        blank=True,
        default="",
        help_text="Не показується на сайті. Потрібен, щоб звірити з замовленням.",
    )
    verified_purchase = models.BooleanField(
        verbose_name="Перевірена покупка",
        default=False,
        help_text="Email збігся з виконаним замовленням на цей товар.",
    )
    #: Abuse handling only — never rendered.
    ip_address = models.GenericIPAddressField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ("-created",)
        verbose_name = "Відгук"
        verbose_name_plural = "Відгуки"
        indexes = [models.Index(fields=["product", "status"])]

    def __str__(self):
        return f"{self.name} · {self.rating}★ · {self.product}"

    @property
    def is_public(self) -> bool:
        return self.status == self.Status.APPROVED


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
    main_sale = models.BooleanField(
        help_text="Позначати тільки якщо має відображатись на головній сторінці",
        default=False,
    )

    def __str__(self):
        return f"Акція до {self.date_end}"
    
    def clean(self):
        if self.main_sale:
            # Check if there is another ProductSale with main_sale = True
            existing_main_sale = ProductSale.objects.filter(main_sale=True).exclude(pk=self.pk)
            if existing_main_sale.exists():
                raise ValidationError("Акція з позначкою main_sale уже існує.")
        super().clean()

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Акція"
        verbose_name_plural = "Акції"


class PromoCode(AbstractCreatedUpdated):
    code = models.CharField(
        verbose_name="Код",
        max_length=115,
        blank=False,
        null=False,
    )
    end_time = models.DateTimeField(
        verbose_name="Дата закінчення",
        blank=True,
        null=True,
        help_text="Порожньо = без терміну дії (діє необмежено в часі).",
    )
    discount = models.PositiveIntegerField(
        verbose_name="Знижка",
        validators=[MaxValueValidator(100)],
        blank=False,
        null=False,
        default=None,
        help_text="У відсотках",
    )
    max_uses_total = models.PositiveIntegerField(
        verbose_name="Макс. використань загалом",
        blank=True,
        null=True,
        help_text="Порожньо = без ліміту. Наприклад 100 — код помре після 100 замовлень.",
    )
    max_uses_per_user = models.PositiveIntegerField(
        verbose_name="Макс. використань на користувача",
        blank=True,
        null=True,
        help_text="Порожньо = без ліміту. 1 = одноразовий на email/акаунт.",
    )

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоди"

    def __str__(self):
        return self.code

    @property
    def is_active(self):
        if self.end_time is None:
            return True
        return self.end_time >= timezone.now()

    def active_redemptions(self):
        from order.models import Order

        return self.redemptions.exclude(order__status=Order.STATUS_CANCELLED)

    def uses_count(self) -> int:
        return self.active_redemptions().count()
