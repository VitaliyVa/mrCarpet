import uuid

from django.db import models

from s_content.models import AbstractCreatedUpdated


# Create your models here.
class ContactRequest(AbstractCreatedUpdated):
    name = models.CharField(max_length=115, verbose_name="Ім'я")
    email = models.EmailField(verbose_name="Пошта")
    text = models.TextField(verbose_name="Коментар")
    created = models.DateTimeField(
        verbose_name="Дата створення",
        auto_now_add=True,
        null=True,
        blank=True
    )
    is_processed = models.BooleanField(
        verbose_name="Оброблено",
        default=False
    )

    class Meta:
        verbose_name = "Контактна форма"
        verbose_name_plural = "Контактні форми"

    def __str__(self):
        return f"Запитання від {self.name}"


class Subscription(models.Model):
    SOURCE_FOOTER = "footer"
    SOURCE_PROFILE = "profile"
    SOURCE_IMPORT = "import"
    SOURCE_CHOICES = (
        (SOURCE_FOOTER, "Футер"),
        (SOURCE_PROFILE, "Кабінет"),
        (SOURCE_IMPORT, "Імпорт"),
    )

    email = models.EmailField(unique=True, verbose_name="Email")
    user = models.ForeignKey(
        verbose_name="Користувач",
        to="users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
    )
    is_active = models.BooleanField(
        verbose_name="Активна підписка",
        default=True,
        db_index=True,
    )
    subscribed_at = models.DateTimeField(
        verbose_name="Підписано",
        auto_now_add=True,
        null=True,
        blank=True,
    )
    unsubscribed_at = models.DateTimeField(
        verbose_name="Відписано",
        null=True,
        blank=True,
    )
    unsubscribe_token = models.UUIDField(
        verbose_name="Токен відписки",
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    source = models.CharField(
        verbose_name="Джерело",
        max_length=32,
        choices=SOURCE_CHOICES,
        default=SOURCE_FOOTER,
        db_index=True,
    )

    def __str__(self):
        state = "активна" if self.is_active else "відписаний"
        return f"{self.email} ({state})"

    class Meta:
        verbose_name = "Підписаний користувач"
        verbose_name_plural = "Підписані користувачі"
        ordering = ("-subscribed_at",)


class StockInquiry(AbstractCreatedUpdated):
    """Запит клієнта про наявність розміру, якого немає на складі."""

    name = models.CharField(max_length=115, verbose_name="Ім'я")
    email = models.EmailField(verbose_name="Email")
    phone = models.CharField(max_length=64, verbose_name="Телефон")
    product = models.ForeignKey(
        to="catalog.Product",
        verbose_name="Товар",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_inquiries",
    )
    product_attr = models.ForeignKey(
        to="catalog.ProductAttribute",
        verbose_name="Варіація / розмір",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_inquiries",
    )
    product_title = models.CharField(
        max_length=512,
        verbose_name="Назва товару",
        blank=True,
        default="",
    )
    size_label = models.CharField(
        max_length=128,
        verbose_name="Розмір",
        blank=True,
        default="",
    )
    is_processed = models.BooleanField(
        verbose_name="Оброблено",
        default=False,
    )

    class Meta:
        verbose_name = "Запит наявності"
        verbose_name_plural = "Запити наявності"
        ordering = ("-created",)

    def __str__(self):
        title = self.product_title or (self.product.title if self.product else "—")
        size = self.size_label or "—"
        return f"{self.name}: {title} ({size})"

    def save(self, *args, **kwargs):
        if self.product and not self.product_title:
            self.product_title = self.product.title
        if self.product_attr and not self.size_label:
            self.size_label = str(self.product_attr.size) if self.product_attr.size else ""
        return super().save(*args, **kwargs)


class SMTPSettings(models.Model):
    port = models.IntegerField(verbose_name="Порт")
    host = models.CharField(verbose_name="Хост", max_length=255)
    server_email = models.EmailField(verbose_name="Email сервера")
    email_host_password = models.CharField(verbose_name="Пароль", max_length=255)
    username = models.CharField(verbose_name="Логін", max_length=255, null=True, blank=True)
    use_tls = models.BooleanField(verbose_name="Використовувати TLS", default=True)
    use_ssl = models.BooleanField(verbose_name="Використовувати SSL", default=False)

    def __str__(self):
        return "Налаштування SMTP"
    
    class Meta:
        verbose_name = "Налаштування SMTP"
        verbose_name_plural = "Налаштування SMTP"

    def save(self, *args, **kwargs):
        if not self.pk and SMTPSettings.objects.exists():
            return
        return super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


DEFAULT_TELEGRAM_WAKE_WORDS = (
    "містер карпет\n"
    "мистер карпет\n"
    "мр карпет\n"
    "містеркарпет\n"
    "mr carpet\n"
    "mrcarpet\n"
    "mr.carpet\n"
    "mr carpet bot"
)


class TelegramSettings(models.Model):
    """Singleton: дублювання заявок/замовлень у Telegram-групу (або чат)."""

    bot_token = models.CharField(
        verbose_name="Bot token",
        max_length=255,
        blank=True,
        default="",
        help_text="Від @BotFather. Формат: 123456:ABC-DEF...",
    )
    chat_id = models.CharField(
        verbose_name="Chat ID",
        max_length=64,
        blank=True,
        default="",
        help_text="ID групи/супергрупи (зазвичай від’ємний, напр. -100123…) або особистого чату.",
    )
    message_thread_id = models.CharField(
        verbose_name="Topic ID (forum)",
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "Для груп з топіками (Topics). "
            "Напиши /start боту всередині потрібного топіку → getUpdates → message_thread_id. "
            "Порожньо = General (часто закритий → TOPIC_CLOSED)."
        ),
    )
    is_enabled = models.BooleanField(
        verbose_name="Увімкнено",
        default=False,
        help_text="Якщо вимкнено — повідомлення не надсилаються.",
    )
    notify_orders = models.BooleanField(
        verbose_name="Замовлення",
        default=True,
    )
    notify_contacts = models.BooleanField(
        verbose_name="Контактні форми",
        default=True,
    )
    notify_stock = models.BooleanField(
        verbose_name="Запити наявності",
        default=True,
    )
    ai_enabled = models.BooleanField(
        verbose_name="AI агент увімкнено",
        default=False,
        help_text="Двосторонній агент (wake words / згадка / reply). Потрібен REPLICATE_API_TOKEN.",
    )
    wake_words = models.TextField(
        verbose_name="Wake words",
        blank=True,
        default=DEFAULT_TELEGRAM_WAKE_WORDS,
        help_text="По одному на рядок. Для wake words у BotFather вимкни Group Privacy.",
    )
    replicate_model = models.CharField(
        verbose_name="Replicate model",
        max_length=255,
        blank=True,
        default="meta/llama-4-scout-instruct",
        help_text=(
            "Slug на Replicate. Рекомендовано: meta/llama-4-scout-instruct "
            "(розумніше за 8B, дешевше за 70B). Альтернативи: "
            "meta/meta-llama-3-8b-instruct (дешевше), "
            "meta/meta-llama-3-70b-instruct (дорожче/розумніше)."
        ),
    )
    webhook_secret = models.CharField(
        verbose_name="Webhook secret",
        max_length=128,
        blank=True,
        default="",
        help_text="X-Telegram-Bot-Api-Secret-Token для prod webhook.",
    )
    ai_rate_limit_per_user = models.PositiveSmallIntegerField(
        verbose_name="AI rate limit / 10 хв",
        default=10,
        help_text="Макс. AI-запитів на одного Telegram user за 10 хвилин.",
    )

    class Meta:
        verbose_name = "Налаштування Telegram"
        verbose_name_plural = "Налаштування Telegram"

    def __str__(self):
        return "Налаштування Telegram"

    def save(self, *args, **kwargs):
        if not self.pk and TelegramSettings.objects.exists():
            return
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_configured(self) -> bool:
        return bool(self.is_enabled and self.bot_token.strip() and self.chat_id.strip())

    @property
    def ai_ready(self) -> bool:
        return bool(self.ai_enabled and self.bot_token.strip() and self.chat_id.strip())

    def get_wake_words(self):
        raw = self.wake_words or DEFAULT_TELEGRAM_WAKE_WORDS
        return [line.strip() for line in raw.splitlines() if line.strip()]


class TelegramPendingAction(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_REJECTED = "rejected"
    STATUS_EXPIRED = "expired"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Очікує"),
        (STATUS_CONFIRMED, "Підтверджено"),
        (STATUS_REJECTED, "Скасовано"),
        (STATUS_EXPIRED, "Протерміновано"),
        (STATUS_FAILED, "Помилка"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool_name = models.CharField(max_length=64)
    args_json = models.JSONField(default=dict)
    description = models.TextField(blank=True, default="")
    created_by_tg_user = models.BigIntegerField(null=True, blank=True)
    chat_id = models.CharField(max_length=64)
    message_thread_id = models.CharField(max_length=32, blank=True, default="")
    telegram_message_id = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    result_text = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram pending action"
        verbose_name_plural = "Telegram pending actions"
        ordering = ("-created",)

    def __str__(self):
        return f"{self.tool_name} ({self.status})"


class TelegramChatMemory(models.Model):
    chat_id = models.CharField(max_length=64, db_index=True)
    thread_id = models.CharField(max_length=32, blank=True, default="", db_index=True)
    summary = models.TextField(blank=True, default="")
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram chat memory"
        verbose_name_plural = "Telegram chat memories"
        unique_together = (("chat_id", "thread_id"),)

    def __str__(self):
        return f"memory {self.chat_id}/{self.thread_id or '-'}"


class TelegramChatMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_TOOL = "tool"
    ROLE_CHOICES = (
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
        (ROLE_TOOL, "Tool"),
    )

    chat_id = models.CharField(max_length=64, db_index=True)
    thread_id = models.CharField(max_length=32, blank=True, default="", db_index=True)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    tg_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Telegram chat message"
        verbose_name_plural = "Telegram chat messages"
        ordering = ("created",)
        indexes = [
            models.Index(fields=["chat_id", "thread_id", "-created"]),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


class TelegramProcessedUpdate(models.Model):
    """Dedupe update_id across workers."""

    update_id = models.BigIntegerField(unique=True, primary_key=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Telegram processed update"
        verbose_name_plural = "Telegram processed updates"


class ShopSettings(models.Model):
    """Singleton: магазинні опції (безкоштовна доставка тощо)."""

    free_shipping_enabled = models.BooleanField(
        verbose_name="Безкоштовна доставка увімкнена",
        default=True,
        help_text="Вимкни — опція зникне з кошика, карток товару й нових замовлень.",
    )
    free_shipping_threshold = models.PositiveIntegerField(
        verbose_name="Поріг безкоштовної доставки (грн)",
        default=1499,
        help_text="Сума товарів (після промокоду), від якої доставка за наш рахунок.",
    )
    delivery_from_price = models.PositiveIntegerField(
        verbose_name="Мін. тариф доставки для UI (грн)",
        default=90,
        help_text="Показується як «Від X грн» і перекреслюється при безкоштовній доставці.",
    )
    novelty_days = models.PositiveIntegerField(
        verbose_name="Новинка: днів від створення",
        default=90,
        help_text=(
            "Бейдж «Новинка» показується, якщо у товару увімкнено прапорець "
            "і з дати створення минуло не більше цієї кількості днів."
        ),
    )

    class Meta:
        verbose_name = "Налаштування магазину"
        verbose_name_plural = "Налаштування магазину"

    def __str__(self):
        return "Налаштування магазину"

    def save(self, *args, **kwargs):
        if not self.pk and ShopSettings.objects.exists():
            return
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class NewsletterCampaign(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_GENERATING = "generating"
    STATUS_READY = "ready"
    STATUS_SENDING = "sending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Чернетка"),
        (STATUS_GENERATING, "Генерація HTML"),
        (STATUS_READY, "Готово до відправки"),
        (STATUS_SENDING, "Відправляється"),
        (STATUS_SENT, "Надіслано"),
        (STATUS_FAILED, "Помилка"),
    )

    subject = models.CharField(verbose_name="Тема листа", max_length=255)
    preheader = models.CharField(
        verbose_name="Preheader",
        max_length=255,
        blank=True,
        default="",
        help_text="Короткий текст у inbox поруч із темою.",
    )
    brief = models.TextField(
        verbose_name="Бриф для AI",
        blank=True,
        default="",
        help_text="Тези акції, CTA URL, тон. Для кнопки «Згенерувати HTML».",
    )
    hero_image = models.ImageField(
        verbose_name="Hero-фото листа",
        upload_to="newsletter/heroes",
        blank=True,
        null=True,
        help_text=(
            "Опційно завантаж своє фото. Якщо порожньо — при генерації "
            "Replicate намалює hero (gpt-image-2 low) і оптимізує у WebP."
        ),
    )
    image_prompt = models.TextField(
        verbose_name="Промпт для фото (AI)",
        blank=True,
        default="",
        help_text="Заповнюється текстовою моделлю під час генерації; можна правити вручну.",
    )
    body_html = models.TextField(
        verbose_name="HTML тіла (inner)",
        blank=True,
        default="",
        help_text="Лише внутрішній контент; shell — emails/base.html.",
    )
    status = models.CharField(
        verbose_name="Статус",
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    created_by = models.ForeignKey(
        verbose_name="Автор",
        to="users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="newsletter_campaigns",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipients_total = models.PositiveIntegerField(default=0)
    recipients_sent = models.PositiveIntegerField(default=0)
    recipients_failed = models.PositiveIntegerField(default=0)
    ai_model = models.CharField(max_length=255, blank=True, default="")
    ai_prompt_snapshot = models.TextField(blank=True, default="")
    test_email = models.EmailField(blank=True, default="")

    class Meta:
        verbose_name = "Розсилка (кампанія)"
        verbose_name_plural = "Розсилки (кампанії)"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.subject} [{self.get_status_display()}]"

    @property
    def is_locked(self) -> bool:
        return self.status in (self.STATUS_SENDING, self.STATUS_SENT)


class NewsletterDelivery(models.Model):
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = (
        (STATUS_SENT, "Надіслано"),
        (STATUS_FAILED, "Помилка"),
        (STATUS_SKIPPED, "Пропущено"),
    )

    campaign = models.ForeignKey(
        NewsletterCampaign,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_SENT, db_index=True
    )
    error = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Доставка розсилки"
        verbose_name_plural = "Доставки розсилок"
        ordering = ("-sent_at",)
        unique_together = (("campaign", "subscription"),)

    def __str__(self):
        return f"{self.campaign_id} → {self.subscription_id} ({self.status})"
