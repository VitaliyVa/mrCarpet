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

    class Status(models.TextChoices):
        DRAFT = "draft", "Чернетка"
        PUBLISHED = "published", "Опубліковано"

    #: Draft by default, and that default is the point. Saving used to publish
    #: instantly — into the page, the sitemap and the category sidebar — so a
    #: half-written article, or the raw output of the generator before anyone
    #: edited it, was live and indexable the moment it was created.
    status = models.CharField(
        verbose_name="Статус",
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(
        verbose_name="Опубліковано",
        null=True,
        blank=True,
        editable=False,
        help_text="Момент першої публікації. Дата в розмітці береться звідси.",
    )

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('article', kwargs={'slug': self.slug})

    @property
    def is_public(self) -> bool:
        return self.status == self.Status.PUBLISHED

    def save(self, *args, **kwargs):
        # Stamped on the first publish only. Editing a live article later must
        # not move its datePublished — Google reads that date, and an article
        # that keeps claiming to be new looks like churn.
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            from django.utils import timezone

            self.published_at = timezone.now()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ("-published_at", "-created")
        verbose_name = "Стаття блогу"
        verbose_name_plural = "Статті блогу"
