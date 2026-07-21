from django.contrib import admin
from django.contrib.auth.models import Group
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from .models import (
    ContactRequest,
    NewsletterCampaign,
    NewsletterDelivery,
    ShopSettings,
    SMTPSettings,
    StockInquiry,
    Subscription,
    TelegramPendingAction,
    TelegramSettings,
)


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "is_active",
        "source",
        "user",
        "subscribed_at",
        "unsubscribed_at",
    )
    list_filter = ("is_active", "source", "subscribed_at")
    search_fields = ("email", "user__email")
    readonly_fields = ("unsubscribe_token", "subscribed_at", "unsubscribed_at")
    raw_id_fields = ("user",)
    ordering = ("-subscribed_at",)
    list_per_page = 50

    def save_model(self, request, obj, form, change):
        """Синхронізувати unsubscribed_at при ручній зміні is_active в адмінці."""
        from django.utils import timezone

        if change and "is_active" in form.changed_data:
            if obj.is_active:
                obj.unsubscribed_at = None
            elif not obj.unsubscribed_at:
                obj.unsubscribed_at = timezone.now()
        super().save_model(request, obj, form, change)


class SMTPSettingsAdmin(admin.ModelAdmin):
    list_display = ["host", "port", "server_email", "username", "use_tls", "use_ssl"]
    fieldsets = (
        (
            "SMTP",
            {
                "description": (
                    "<b>Рекомендовано на DigitalOcean (безкоштовно): Brevo</b><br>"
                    "Порт 587 до Gmail з дропа заблокований — використовуй relay на <b>2525</b>.<br><br>"
                    "1) Зареєструйся на <a href='https://www.brevo.com/' target='_blank'>brevo.com</a> (free ≈ 300 листів/день).<br>"
                    "2) SMTP &amp; API → SMTP → створи SMTP key.<br>"
                    "3) Заповни поля нижче:<br>"
                    "• Host = <code>smtp-relay.brevo.com</code><br>"
                    "• Port = <code>2525</code><br>"
                    "• TLS = увімкнено, SSL = вимкнено<br>"
                    "• Логін = SMTP login з Brevo (зазвичай твій email акаунта)<br>"
                    "• Пароль = SMTP key<br>"
                    "• Email сервера (From) = верифікований у Brevo адрес "
                    "(спочатку можна той самий login; для продакшену — свій домен).<br><br>"
                    "Перевірка: <code>python manage.py send_smtp_test you@email.com</code><br><br>"
                    "<i>Gmail smtp.gmail.com:587 на цьому сервері не працює (Network unreachable).</i>"
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
                "fields": (
                    "is_enabled",
                    "bot_token",
                    "chat_id",
                    "message_thread_id",
                    "listen_thread_ids",
                ),
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


class ShopSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "free_shipping_enabled",
        "free_shipping_threshold",
        "delivery_from_price",
        "novelty_days",
    ]
    fieldsets = (
        (
            "Безкоштовна доставка",
            {
                "description": (
                    "Керує кошиком, карткою товару, SEO-текстами та прапорцем у замовленнях. "
                    "Вимкни «увімкнена» — опція зникне без деплою. "
                    "Поріг рахується від суми товарів після промокоду. "
                    "Сума LiqPay не змінюється — доставку компенсуємо операційно."
                ),
                "fields": (
                    "free_shipping_enabled",
                    "free_shipping_threshold",
                    "delivery_from_price",
                ),
            },
        ),
        (
            "Новинка",
            {
                "description": (
                    "Бейдж на картці товару: прапорець «Новинка» у товарі "
                    "+ не більше N днів від дати створення. "
                    "Після строку бейдж зникає сам (прапорець у БД можна не чіпати)."
                ),
                "fields": ("novelty_days",),
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return ShopSettings.objects.count() == 0

    def has_change_permission(self, request, obj=None):
        return True


@admin.register(NewsletterCampaign)
class NewsletterCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "status",
        "recipients_sent",
        "recipients_total",
        "created_at",
        "sent_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("subject", "brief")
    readonly_fields = (
        "status",
        "created_at",
        "updated_at",
        "sent_at",
        "recipients_total",
        "recipients_sent",
        "recipients_failed",
        "ai_model",
        "ai_prompt_snapshot",
        "created_by",
        "admin_actions_panel",
    )
    fieldsets = (
        (
            "Кампанія",
            {
                "fields": (
                    "subject",
                    "preheader",
                    "brief",
                    "hero_image",
                    "image_prompt",
                    "body_html",
                    "test_email",
                    "status",
                    "admin_actions_panel",
                ),
                "description": (
                    "1) Збережи чернетку → 2) (опц.) завантаж hero → "
                    "3) Згенеруй HTML+фото (Replicate) → "
                    "4) Перегляд → 5) Тест → 6) Надіслати всім активним."
                ),
            },
        ),
        (
            "Прогрес / AI",
            {
                "classes": ("collapse",),
                "fields": (
                    "recipients_total",
                    "recipients_sent",
                    "recipients_failed",
                    "ai_model",
                    "ai_prompt_snapshot",
                    "created_by",
                    "created_at",
                    "updated_at",
                    "sent_at",
                ),
            },
        ),
    )

    class Media:
        js = ("admin/js/replicate_generate_newsletter.js",)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        if obj.body_html and obj.status == NewsletterCampaign.STATUS_DRAFT:
            obj.status = NewsletterCampaign.STATUS_READY
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        base = list(super().get_readonly_fields(request, obj))
        if obj and obj.status in (
            NewsletterCampaign.STATUS_SENT,
            NewsletterCampaign.STATUS_SENDING,
        ):
            base.extend(
                [
                    "subject",
                    "preheader",
                    "brief",
                    "hero_image",
                    "image_prompt",
                    "body_html",
                    "test_email",
                ]
            )
        return list(dict.fromkeys(base))

    @admin.display(description="Дії")
    def admin_actions_panel(self, obj):
        if not obj or not obj.pk:
            return "Збережіть кампанію, щоб з’явились кнопки."
        from django.utils.html import format_html

        return format_html(
            '<div class="newsletter-admin-actions" data-campaign-id="{}">'
            '<p><b>Активних підписників:</b> {}</p>'
            '<button type="button" class="button" id="newsletter-generate-btn">'
            "Згенерувати HTML (Replicate)</button> "
            '<a class="button" href="{}" target="_blank">Перегляд</a> '
            '<button type="button" class="button" id="newsletter-test-btn">'
            "Тест собі</button> "
            '<button type="button" class="button default" id="newsletter-send-btn">'
            "Надіслати всім активним</button>"
            '<p id="newsletter-admin-status" style="margin-top:10px;"></p>'
            "</div>",
            obj.pk,
            Subscription.objects.filter(is_active=True).count(),
            reverse("admin:project_newslettercampaign_preview", args=[obj.pk]),
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/generate-html/",
                self.admin_site.admin_view(self.generate_html_view),
                name="project_newslettercampaign_generate",
            ),
            path(
                "<path:object_id>/preview/",
                self.admin_site.admin_view(self.preview_view),
                name="project_newslettercampaign_preview",
            ),
            path(
                "<path:object_id>/test-send/",
                self.admin_site.admin_view(self.test_send_view),
                name="project_newslettercampaign_test",
            ),
            path(
                "<path:object_id>/mass-send/",
                self.admin_site.admin_view(self.mass_send_view),
                name="project_newslettercampaign_send",
            ),
        ]
        return custom + urls

    @method_decorator(require_POST)
    def generate_html_view(self, request, object_id):
        from project.services.newsletter_generate import (
            NewsletterGenerationError,
            ReplicateNewsletterService,
        )

        campaign = get_object_or_404(NewsletterCampaign, pk=object_id)
        if campaign.is_locked:
            return JsonResponse(
                {"success": False, "error": "Кампанія заблокована для змін"},
                status=400,
            )
        # Sync fields from open admin form (may be unsaved)
        if "subject" in request.POST:
            campaign.subject = (request.POST.get("subject") or campaign.subject)[:255]
        if "preheader" in request.POST:
            campaign.preheader = (request.POST.get("preheader") or "")[:255]
        if "brief" in request.POST:
            campaign.brief = request.POST.get("brief") or ""
        if "image_prompt" in request.POST:
            campaign.image_prompt = request.POST.get("image_prompt") or ""
        campaign.save()
        try:
            result = ReplicateNewsletterService().generate_for_campaign(campaign)
        except NewsletterGenerationError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
        except Exception:
            import logging

            logging.getLogger("project.newsletter_generate").exception(
                "newsletter generate failed"
            )
            return JsonResponse(
                {"success": False, "error": "Несподівана помилка Replicate"},
                status=500,
            )
        campaign.refresh_from_db()
        hero_url = ""
        if campaign.hero_image:
            hero_url = campaign.hero_image.url
        return JsonResponse(
            {
                "success": True,
                "subject": campaign.subject,
                "preheader": campaign.preheader,
                "body_html": campaign.body_html,
                "image_prompt": campaign.image_prompt,
                "hero_image_url": hero_url,
                "image_generated": result.image_generated,
                "status": campaign.status,
                "duration_sec": result.duration_sec,
                "model": result.model,
            }
        )

    def preview_view(self, request, object_id):
        from project.services.newsletter_render import render_campaign_preview

        campaign = get_object_or_404(NewsletterCampaign, pk=object_id)
        html = render_campaign_preview(campaign)
        return HttpResponse(html)

    @method_decorator(require_POST)
    def test_send_view(self, request, object_id):
        from project.services.newsletter_send import (
            NewsletterSendError,
            send_campaign_test,
        )

        campaign = get_object_or_404(NewsletterCampaign, pk=object_id)
        to_email = (
            request.POST.get("email")
            or campaign.test_email
            or getattr(request.user, "email", "")
        )
        try:
            send_campaign_test(campaign, to_email)
        except NewsletterSendError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            return JsonResponse(
                {"success": False, "error": str(exc)}, status=500
            )
        return JsonResponse(
            {
                "success": True,
                "message": f"Тестовий лист надіслано на {to_email}",
            }
        )

    @method_decorator(require_POST)
    def mass_send_view(self, request, object_id):
        from project.services.newsletter_send import (
            NewsletterSendError,
            start_mass_send,
        )

        campaign = get_object_or_404(NewsletterCampaign, pk=object_id)
        try:
            n = start_mass_send(campaign)
        except NewsletterSendError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
        return JsonResponse(
            {
                "success": True,
                "message": f"Розсилка запущена на {n} активних підписників",
                "recipients": n,
            }
        )


@admin.register(NewsletterDelivery)
class NewsletterDeliveryAdmin(admin.ModelAdmin):
    list_display = ("campaign", "subscription", "status", "sent_at")
    list_filter = ("status", "sent_at")
    search_fields = ("subscription__email", "campaign__subject")
    readonly_fields = ("campaign", "subscription", "status", "error", "sent_at")

    def has_add_permission(self, request):
        return False


admin.site.register(SMTPSettings, SMTPSettingsAdmin)
admin.site.register(TelegramSettings, TelegramSettingsAdmin)
admin.site.register(ShopSettings, ShopSettingsAdmin)
admin.site.register(ContactRequest, ContactRequestAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.unregister(Group)
