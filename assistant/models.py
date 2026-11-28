import uuid

from django.conf import settings as dj_settings
from django.db import models


class AssistantSettings(models.Model):
    """Singleton: the site chat bot switch, its key and spend limits."""

    MODEL_HAIKU = "claude-haiku-5-5"
    MODEL_SONNET = "claude-sonnet-5-5"
    MODEL_CHOICES = (
        (MODEL_HAIKU, "Claude Haiku 5.5 (дешевий, швидкий)"),
        (MODEL_SONNET, "Claude Sonnet 5.5 (розумніший, у ~20 разів дорожчий)"),
    )

    enabled = models.BooleanField(
        verbose_name="Чат-бот увімкнений",
        default=False,
        help_text="Кнопка чату з'являється на сайті, коли бот увімкнений і є ключ API.",
    )
    api_key = models.CharField(
        verbose_name="Ключ Anthropic API",
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Ключ з console.anthropic.com (починається з sk-ant-). "
            "Порожньо: береться ANTHROPIC_API_KEY з .env сервера."
        ),
    )
    model = models.CharField(
        verbose_name="Модель",
        max_length=64,
        choices=MODEL_CHOICES,
        default=MODEL_HAIKU,
    )
    daily_budget_usd = models.DecimalField(
        verbose_name="Ліміт витрат на день, $",
        max_digits=6,
        decimal_places=2,
        default=2,
        help_text="Коли за добу витрачено більше, бот просить подзвонити, а не відповідає.",
    )
    messages_per_hour = models.PositiveIntegerField(
        verbose_name="Повідомлень від одного відвідувача за годину",
        default=30,
    )

    class Meta:
        verbose_name = "Налаштування чат-бота"
        verbose_name_plural = "Налаштування чат-бота"

    def __str__(self):
        return "Налаштування чат-бота"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def resolved_api_key(self) -> str:
        return (self.api_key or "").strip() or (
            getattr(dj_settings, "ANTHROPIC_API_KEY", "") or ""
        ).strip()

    @property
    def is_live(self) -> bool:
        return bool(self.enabled and self.resolved_api_key())


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_key = models.CharField(
        verbose_name="Сесія", max_length=64, blank=True, default="", db_index=True
    )
    client_hash = models.CharField(
        verbose_name="Відвідувач (хеш IP)", max_length=64, blank=True, default="", db_index=True
    )
    created = models.DateTimeField(verbose_name="Почато", auto_now_add=True, db_index=True)
    updated = models.DateTimeField(verbose_name="Оновлено", auto_now=True)
    # Raw Messages API history (assistant turns with tool_use / tool_result
    # blocks), so the next request continues the same conversation.
    api_messages = models.JSONField(default=list, blank=True)
    # The order card last shown to the buyer, waiting for the button.
    pending_order = models.JSONField(default=dict, blank=True)
    order = models.ForeignKey(
        verbose_name="Замовлення",
        to="order.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_conversations",
    )
    cards_shown = models.PositiveSmallIntegerField(
        verbose_name="Показано карток замовлення", default=0
    )
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(
        verbose_name="Витрачено, $", max_digits=8, decimal_places=5, default=0
    )

    class Meta:
        verbose_name = "Розмова з чат-ботом"
        verbose_name_plural = "Розмови з чат-ботом"
        ordering = ["-updated"]

    def __str__(self):
        first = self.messages.filter(role=Message.ROLE_USER).first()
        text = first.content[:60] if first else "порожня"
        return f"{self.created:%d.%m %H:%M} · {text}"


class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = ((ROLE_USER, "Покупець"), (ROLE_ASSISTANT, "Бот"))

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(verbose_name="Хто", max_length=16, choices=ROLE_CHOICES)
    content = models.TextField(verbose_name="Текст", blank=True, default="")
    # Cards shown under the message: products, the order summary.
    payload = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Повідомлення"
        verbose_name_plural = "Повідомлення"
        ordering = ["created", "id"]

    def __str__(self):
        return f"{self.get_role_display()}: {self.content[:60]}"
