import io
import logging

from django import forms
from django.contrib import admin, messages
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import Order, PromoCodeRedemption

logger = logging.getLogger(__name__)


def _cancel_reason_choices():
    from project.rozetka_status import CANCEL_REASONS, CANCEL_SKIP

    return (
        [("", "— оберіть причину —")]
        + [(str(pk), label) for pk, label in CANCEL_REASONS]
        + [(CANCEL_SKIP, "Не передавати на Rozetka (вже скасовано в кабінеті)")]
    )


class OrderAdminForm(forms.ModelForm):
    rozetka_cancel_reason = forms.ChoiceField(
        label="Причина скасування для Rozetka",
        required=False,
        choices=_cancel_reason_choices,
        help_text=(
            "Потрібна, коли замовлення з Rozetka переводите в «Скасовано»: "
            "Rozetka отримає саме цю причину."
        ),
    )

    class Meta:
        model = Order
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        order = self.instance
        if not (order and order.pk and order.source == Order.SOURCE_ROZETKA
                and order.rozetka_order_id):
            return cleaned
        before = (
            Order.objects.filter(pk=order.pk).values_list("status", flat=True).first()
        )
        status = cleaned.get("status")
        if (
            status == Order.STATUS_SHIPPED
            and before != Order.STATUS_SHIPPED
            and not (cleaned.get("ttn") or "").strip()
        ):
            self.add_error(
                "ttn", "Rozetka не прийме «Відправлено» без ТТН. Впишіть номер накладної."
            )
        if (
            status == Order.STATUS_CANCELLED
            and before != Order.STATUS_CANCELLED
            and not cleaned.get("rozetka_cancel_reason")
        ):
            self.add_error(
                "rozetka_cancel_reason",
                "Оберіть причину: Rozetka без неї не скасує замовлення.",
            )
        return cleaned


class AdClickFilter(admin.SimpleListFilter):
    title = "Клік з Google Ads"
    parameter_name = "ad_click"

    def lookups(self, request, model_admin):
        return (("yes", "Є"), ("no", "Немає"))

    def queryset(self, request, queryset):
        has_click = ~Q(gclid="") | ~Q(gbraid="") | ~Q(wbraid="")
        if self.value() == "yes":
            return queryset.filter(has_click)
        if self.value() == "no":
            return queryset.exclude(has_click)
        return queryset


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = (
        "order_number",
        "status_badge",
        "customer",
        "phone",
        "email",
        "city",
        "payment_type",
        "promocode_badge",
        "free_shipping_badge",
        "total_price_display",
        "created",
    )
    list_display_links = ("order_number", "customer")
    list_filter = (
        "status",
        "source",
        "payment_type",
        "free_shipping",
        AdClickFilter,
        "utm_source",
        "promocode",
        "city",
        "created",
    )
    actions = ("export_ads_conversions", "confirm_on_rozetka")
    search_fields = (
        "order_number",
        "name",
        "surname",
        "email",
        "phone",
        "city",
        "address",
        "promocode_code",
        "promocode__code",
        "gclid",
        "ttn",
    )
    date_hierarchy = "created"
    ordering = ("-created",)
    list_per_page = 50
    readonly_fields = (
        "order_number",
        "created",
        "updated",
        "np_status",
        "np_checked_at",
        "np_arrived_at",
        "shipped_email_sent_at",
        "stock_returned",
        "promocode_code",
        "promocode_discount",
        "gclid",
        "gbraid",
        "wbraid",
        "ad_click_at",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "ga4_mp_sent",
        "review_request_sent_at",
        "review_links",
        "source",
        "rozetka_order_id",
    )
    list_select_related = ("promocode",)

    fieldsets = (
        (
            "Замовлення",
            {
                "fields": (
                    "order_number",
                    "status",
                    "payment_type",
                    "total_price",
                    "promocode",
                    "promocode_code",
                    "promocode_discount",
                    "created",
                    "updated",
                )
            },
        ),
        (
            "Клієнт",
            {
                "fields": (
                    "name",
                    "surname",
                    "email",
                    "phone",
                )
            },
        ),
        (
            "Доставка (Нова Пошта)",
            {
                "fields": (
                    "city",
                    "address",
                    "ttn",
                    "np_status",
                    "np_checked_at",
                    "np_arrived_at",
                    "shipped_email_sent_at",
                    "stock_returned",
                    "message",
                    "free_shipping",
                    "free_shipping_threshold",
                ),
                "description": (
                    "Місто + відділення НП (поле «Відділення НП»). "
                    "Якщо «Безкоштовна доставка» — оплачуємо НП за клієнта "
                    "(сума товарів ≥ порогу на момент замовлення)."
                ),
            },
        ),
        (
            "Реклама: звідки прийшов покупець",
            {
                "classes": ("collapse",),
                "fields": (
                    "gclid",
                    "gbraid",
                    "wbraid",
                    "ad_click_at",
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                    "ga4_mp_sent",
                ),
                "description": (
                    "Заповнюється сам при оформленні. gclid потрібен, щоб "
                    "завантажити оплачене замовлення в Google Ads як конверсію "
                    "(дія «Вивантажити для Google Ads» у списку або команда "
                    "export_ads_conversions). Для оплати при отриманні покупка "
                    "йде в GA4 лише після статусу «Оплачено» чи «Виконано»."
                ),
            },
        ),
        (
            "Відгук",
            {
                "fields": ("review_request_sent_at", "review_links"),
                "description": (
                    "Посилання відкриває форму відгуку вже з іменем покупця, "
                    "і відгук одразу публікується як перевірена покупка. "
                    "Для замовлень без email його можна переслати у Viber чи Telegram."
                ),
            },
        ),
    )

    ROZETKA_FIELDSET = (
        "Rozetka",
        {
            "fields": ("source", "rozetka_order_id", "rozetka_cancel_reason"),
            "description": (
                "Статус сам передається на Rozetka: «Оплачено, комплектується» → "
                "«Комплектується», «Відправлено» → «Передано в службу доставки» з ТТН, "
                "«Скасовано» → обрана причина. Результат з'являється рядком "
                "«Rozetka ✓ / ✗» у полі «Повідомлення» (оновіть сторінку за кілька секунд)."
            ),
        },
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None and obj.source == Order.SOURCE_ROZETKA:
            return (self.ROZETKA_FIELDSET,) + tuple(fieldsets)
        return fieldsets

    def save_model(self, request, obj, form, change):
        before = None
        if change and obj.pk:
            before = Order.objects.filter(pk=obj.pk).values("status", "ttn").first()
        super().save_model(request, obj, form, change)
        try:
            from project import rozetka_status

            push = rozetka_status.push_for_change(
                obj, before, form.cleaned_data.get("rozetka_cancel_reason", "")
            )
            if push is not None:
                rozetka_status.schedule(obj.pk, push)
                self.message_user(
                    request,
                    f"Rozetka: передаємо статус «{push.label}». Результат буде "
                    "в полі «Повідомлення» за кілька секунд.",
                    messages.INFO,
                )
        except Exception:
            logger.exception("rozetka: could not schedule status push for order %s", obj.pk)
            self.message_user(
                request,
                "Замовлення збережено, але статус на Rozetka не передано. "
                "Змініть його в кабінеті Rozetka.",
                messages.WARNING,
            )

    @admin.action(description="Підтвердити на Rozetka (статус «Опрацьовується менеджером»)")
    def confirm_on_rozetka(self, request, queryset):
        from project import rozetka_status

        selected = queryset.count()
        pks = list(
            queryset.filter(
                source=Order.SOURCE_ROZETKA,
                rozetka_order_id__isnull=False,
                status__in=(Order.STATUS_NEW, Order.STATUS_AWAITING_PAYMENT),
            ).values_list("pk", flat=True)
        )
        skipped = selected - len(pks)
        if pks:
            rozetka_status.schedule_many(pks, rozetka_status.confirm_push())
            self.message_user(
                request,
                f"Rozetka: підтверджуємо {len(pks)} замовл. у фоні. Результат буде "
                "в полі «Повідомлення» кожного замовлення.",
                messages.INFO,
            )
        if skipped:
            self.message_user(
                request,
                f"Пропущено {skipped}: не з Rozetka або вже не в статусі «Нове» / «Очікує оплати».",
                messages.WARNING,
            )

    @admin.action(description="Вивантажити для Google Ads (CSV, лише оплачені з gclid)")
    def export_ads_conversions(self, request, queryset):
        from .ads_conversions import conversion_rows, write_csv

        rows = conversion_rows(queryset, with_braid=False)
        buf = io.StringIO()
        write_csv(buf, rows)
        stamp = timezone.now().strftime("%Y%m%d-%H%M")
        response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="ads-conversions-{stamp}.csv"'
        )
        return response

    @admin.display(description="Посилання для відгуку")
    def review_links(self, obj):
        if not obj or not obj.pk or obj.status not in (
            Order.STATUS_SHIPPED,
            Order.STATUS_COMPLETED,
        ):
            return "З'явиться, коли замовлення буде відправлене."
        from order.review_request import products_in, review_url

        products = products_in(obj)
        if not products:
            return "У замовленні немає товарів."
        return format_html_join(
            "",
            '<div style="margin-bottom:6px"><b>{}</b><br>'
            '<input type="text" readonly value="{}" style="width:100%;max-width:640px" '
            'onclick="this.select()"></div>',
            ((p.title, review_url(obj, p)) for p in products),
        )

    @admin.display(description="Клієнт", ordering="name")
    def customer(self, obj):
        return f"{obj.name} {obj.surname}".strip()

    @admin.display(description="Сума", ordering="total_price")
    def total_price_display(self, obj):
        if obj.total_price is None:
            return "—"
        return f"{obj.total_price:.0f} грн"

    @admin.display(description="Промокод", ordering="promocode_code")
    def promocode_badge(self, obj):
        label = obj.promocode_label
        if not label:
            return "—"
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
            'background:#a46c46;color:#fff;font-size:12px;white-space:nowrap;">{}</span>',
            label,
        )

    @admin.display(description="Доставка", ordering="free_shipping", boolean=False)
    def free_shipping_badge(self, obj):
        if obj.free_shipping:
            threshold = obj.free_shipping_threshold
            label = f"Безкошт.{f' від {threshold}' if threshold else ''}"
            return format_html(
                '<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
                'background:#198754;color:#fff;font-size:12px;white-space:nowrap;">{}</span>',
                label,
            )
        return "—"

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj):
        colors = {
            Order.STATUS_NEW: "#0d6efd",
            Order.STATUS_AWAITING_PAYMENT: "#fd7e14",
            Order.STATUS_PAID: "#198754",
            Order.STATUS_SHIPPED: "#6f42c1",
            Order.STATUS_COMPLETED: "#20c997",
            Order.STATUS_CANCELLED: "#6c757d",
        }
        color = colors.get(obj.status, "#453f3a")
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
            'background:{};color:#fff;font-size:12px;white-space:nowrap;">{}</span>',
            color,
            obj.get_status_display(),
        )


@admin.register(PromoCodeRedemption)
class PromoCodeRedemptionAdmin(admin.ModelAdmin):
    list_display = ("promocode", "order", "email", "user", "created")
    list_filter = ("promocode", "created")
    search_fields = (
        "email",
        "promocode__code",
        "order__order_number",
    )
    readonly_fields = ("created", "updated")
    raw_id_fields = ("order", "user", "promocode")
    date_hierarchy = "created"
