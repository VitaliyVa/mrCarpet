from django.contrib import admin
from django.utils.html import format_html

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "status_badge",
        "customer",
        "phone",
        "email",
        "city",
        "payment_type",
        "free_shipping_badge",
        "total_price_display",
        "created",
    )
    list_display_links = ("order_number", "customer")
    list_filter = (
        "status",
        "payment_type",
        "free_shipping",
        "city",
        "created",
    )
    search_fields = (
        "order_number",
        "name",
        "surname",
        "email",
        "phone",
        "city",
        "address",
    )
    date_hierarchy = "created"
    ordering = ("-created",)
    list_per_page = 50
    readonly_fields = ("order_number", "created", "updated")
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
            "Доставка",
            {
                "fields": (
                    "city",
                    "address",
                    "message",
                    "free_shipping",
                    "free_shipping_threshold",
                ),
                "description": (
                    "Якщо «Безкоштовна доставка» — оплачуємо НП за клієнта "
                    "(сума товарів ≥ порогу на момент замовлення)."
                ),
            },
        ),
    )

    @admin.display(description="Клієнт", ordering="name")
    def customer(self, obj):
        return f"{obj.name} {obj.surname}".strip()

    @admin.display(description="Сума", ordering="total_price")
    def total_price_display(self, obj):
        if obj.total_price is None:
            return "—"
        return f"{obj.total_price:.0f} грн"

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
