from django.contrib import admin
from django.contrib.auth.models import Group

from .models import (
    ContactRequest,
    SMTPSettings,
    StockInquiry,
    Subscription,
    TelegramPendingAction,
    TelegramSettings,
)


class SMTPSettingsAdmin(admin.ModelAdmin):
    list_display = ["host", "port", "server_email", "username", "use_tls", "use_ssl"]
    fieldsets = (
        (
            "SMTP (Gmail)",
            {
                "description": (
                    "Для Gmail: Host = smtp.gmail.com, Port = 587, TLS = увімкнено, SSL = вимкнено. "
                    "У полі «Пароль» потрібен App Password (не звичайний пароль акаунта). "
                    "Створити: Google Account → Security → 2-Step Verification → App passwords."
                ),
                "fields": (
                    "host",
                    "port",
                    "server_email",
                    "username",
                    "email_host_password",
                    "use_tls",
                    "use_ssl",
                ),
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return SMTPSettings.objects.count() == 0

    def has_change_permission(self, request, obj=None):
        return True


class TelegramSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "is_enabled",
        "ai_enabled",
        "chat_id",
        "notify_orders",
        "notify_contacts",
        "notify_stock",
    ]
    fieldsets = (
        (
            "Telegram Bot",
            {
                "description": (
                    "1) Створи бота в @BotFather → скопіюй token. "
                    "2) Додай бота в групу (краще адміном). "
                    "3) Для AI wake words у BotFather вимкни Group Privacy. "
                    "4) Chat ID / Topic ID з getUpdates. "
                    "5) Увімкни «Увімкнено» (нотифікації) і/або «AI агент»."
                ),
                "fields": ("is_enabled", "bot_token", "chat_id", "message_thread_id"),
            },
        ),
        (
            "Що надсилати (нотифікації)",
            {
                "fields": ("notify_orders", "notify_contacts", "notify_stock"),
            },
        ),
        (
            "AI агент",
            {
                "description": (
                    "Потрібен REPLICATE_API_TOKEN у .env. "
                    "Local: python manage.py telegram_poll. "
                    "Prod: python manage.py telegram_set_webhook "
                    "https://mrcarpet24.com/api/telegram/webhook/"
                ),
                "fields": (
                    "ai_enabled",
                    "wake_words",
                    "replicate_model",
                    "webhook_secret",
                    "ai_rate_limit_per_user",
                ),
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return TelegramSettings.objects.count() == 0

    def has_change_permission(self, request, obj=None):
        return True


class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "text", "is_processed", "created"]
    search_fields = ["name", "email", "text"]
    list_filter = ["created"]
    date_hierarchy = "created"
    ordering = ["-created"]
    readonly_fields = ["created", "email", "text", "name"]

    def has_delete_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True


@admin.register(StockInquiry)
class StockInquiryAdmin(admin.ModelAdmin):
    list_display = (
        "created",
        "name",
        "phone",
        "email",
        "product_title",
        "size_label",
        "is_processed",
    )
    list_filter = ("is_processed", "created")
    search_fields = ("name", "email", "phone", "product_title", "size_label")
    date_hierarchy = "created"
    ordering = ("-created",)
    list_editable = ("is_processed",)
    readonly_fields = (
        "created",
        "updated",
        "name",
        "email",
        "phone",
        "product",
        "product_attr",
        "product_title",
        "size_label",
    )
    list_per_page = 50

    def has_add_permission(self, request):
        return False


@admin.register(TelegramPendingAction)
class TelegramPendingActionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tool_name",
        "status",
        "chat_id",
        "created_by_tg_user",
        "expires_at",
        "created",
    )
    list_filter = ("status", "tool_name", "created")
    search_fields = ("id", "description", "chat_id")
    readonly_fields = (
        "id",
        "tool_name",
        "args_json",
        "description",
        "created_by_tg_user",
        "chat_id",
        "message_thread_id",
        "telegram_message_id",
        "status",
        "result_text",
        "expires_at",
        "created",
        "updated",
    )

    def has_add_permission(self, request):
        return False


admin.site.register(SMTPSettings, SMTPSettingsAdmin)
admin.site.register(TelegramSettings, TelegramSettingsAdmin)
admin.site.register(ContactRequest, ContactRequestAdmin)
admin.site.register(Subscription)
admin.site.unregister(Group)
