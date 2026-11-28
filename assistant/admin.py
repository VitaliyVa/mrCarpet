from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import AssistantSettings, Conversation, Message


class AssistantSettingsForm(forms.ModelForm):
    api_key = forms.CharField(
        label="Ключ Anthropic API",
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text=AssistantSettings._meta.get_field("api_key").help_text,
    )

    class Meta:
        model = AssistantSettings
        fields = "__all__"


@admin.register(AssistantSettings)
class AssistantSettingsAdmin(admin.ModelAdmin):
    form = AssistantSettingsForm
    list_display = ("__str__", "enabled", "model", "daily_budget_usd")

    def has_add_permission(self, request):
        return not AssistantSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("created", "role", "content")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "message_count", "order_link", "cost_usd", "updated")
    list_filter = ("created",)
    readonly_fields = ("id", "created", "updated", "order", "input_tokens", "output_tokens", "cost_usd")
    exclude = ("api_messages", "pending_order", "session_key", "client_hash")
    inlines = [MessageInline]
    date_hierarchy = "created"

    @admin.display(description="Повідомлень")
    def message_count(self, obj):
        return obj.messages.count()

    @admin.display(description="Замовлення")
    def order_link(self, obj):
        if not obj.order_id:
            return "—"
        return format_html(
            '<a href="/admin/order/order/{}/change/">№{}</a>', obj.order_id, obj.order.order_number
        )

    def has_add_permission(self, request):
        return False
