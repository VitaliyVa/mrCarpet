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


class ArticleTopic(models.Model):
    """
    The backlog the weekly generator draws from, best first.

    A stored, ranked queue rather than asking a model to invent a topic each
    week: left to improvise, it drifts toward whatever is easy to write, and
    the posts that actually earn traffic — the ones tied to a real search and
    a real category page — never get written.

    `rank` is the running order. Lower goes first, so the strongest topics
    land in the weeks when there is least else on the blog to rank for.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "У черзі"
        USED = "used", "Використана"
        SKIPPED = "skipped", "Пропущена"

    title = models.CharField(verbose_name="Тема", max_length=300)
    brief = models.TextField(
        verbose_name="Що розкрити",
        blank=True,
        default="",
        help_text="Кут подачі для генератора: що саме має бути в статті.",
    )
    target_path = models.CharField(
        verbose_name="Куди вести",
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Шлях категорії або сторінки, на яку стаття має посилатись, "
            "напр. /catalog/categorie/v-ditiachu/. Це і є сенс статті."
        ),
    )
    rank = models.PositiveIntegerField(
        verbose_name="Черга",
        default=1000,
        db_index=True,
        help_text="Менше = раніше. Найсильніші теми йдуть першими.",
    )
    status = models.CharField(
        verbose_name="Статус",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    article = models.ForeignKey(
        "blog.Article",
        verbose_name="Стаття",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="topics",
    )
    used_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ("rank", "pk")
        verbose_name = "Тема для блогу"
        verbose_name_plural = "Теми для блогу"
        indexes = [models.Index(fields=["status", "rank"])]

    def __str__(self):
        return f"{self.rank}. {self.title}"

    @classmethod
    def next_pending(cls):
        return cls.objects.filter(status=cls.Status.PENDING).order_by("rank", "pk").first()
