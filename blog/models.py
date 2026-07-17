from django.db import models
from django.urls import reverse
from s_content.models import AbstractCreatedUpdated, AbstractMetaTags, AbstractTitleSlug


class Article(AbstractCreatedUpdated, AbstractMetaTags, AbstractTitleSlug):
    description = models.TextField(
        verbose_name='Description', blank=True, null=True
    )
    image = models.ImageField(
        max_length=512,
        blank=True,
        null=True,
        upload_to='articles'
    )

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('article', kwargs={'slug': self.slug})

    class Meta:
        verbose_name = "Стаття блогу"
        verbose_name_plural = "Статті блогу"
