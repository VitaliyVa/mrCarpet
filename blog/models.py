from django.db import models
from s_content.models import AbstractCreatedUpdated, AbstractMetaTags, AbstractTitleSlug

# Create your models here.
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