from django.db import models
from s_utils.model_fields import generate_slug

# Create your models here.
class AbstractCreatedUpdated(models.Model):
    created = models.DateTimeField(
        verbose_name='Created', auto_now_add=True, blank=True, null=True
    )
    updated = models.DateTimeField(
        verbose_name='Updated', auto_now=True, blank=True, null=True
    )

    class Meta:
        abstract = True


class AbstractMetaTags(models.Model):
    meta_title = models.TextField(
        verbose_name='SEO Title',
        blank=True,
        null=True,
        help_text=(
            'Title у вкладці браузера / сніпеті. '
            'Якщо порожньо — використовується назва (title).'
        ),
    )
    meta_description = models.TextField(
        verbose_name='SEO Description',
        blank=True,
        null=True,
        help_text=(
            'Короткий опис для сніпета (~150–160 символів). '
            'Пишіть як відповідь на інтент покупця, не keyword soup. '
            'Якщо порожньо — fallback з опису / бренду.'
        ),
    )
    meta_keys = models.TextField(
        verbose_name='SEO Keywords',
        blank=True,
        null=True,
        help_text='Опційно. Google майже ігнорує; можна залишити порожнім.',
    )

    class Meta:
        abstract = True


class AbstractTitleSlug(models.Model):
    title = models.CharField(
        verbose_name='Title', max_length=512, blank=True, null=True
    )
    slug = models.CharField(
        verbose_name='Unique label',
        max_length=512,
        blank=True,
        null=True,
        help_text='Created automatically'
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.slug = generate_slug(self)
        return super().save()