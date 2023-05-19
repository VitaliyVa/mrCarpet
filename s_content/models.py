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
        verbose_name='Meta Title', blank=True, null=True
    )
    meta_description = models.TextField(
        verbose_name='Meta Description', blank=True, null=True
    )
    meta_keys = models.TextField(
        verbose_name='Meta Keys', blank=True, null=True
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