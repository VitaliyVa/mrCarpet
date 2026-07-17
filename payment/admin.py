from django import forms
from django.contrib import admin

from .models import Payment, LiqPaySettings


class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'status', 'amount', 'currency', 'timestamp']
    list_filter = ['status', 'currency', 'timestamp']
    search_fields = ['order__order_number', 'order__id', 'status']
    readonly_fields = ['timestamp']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('order')


class LiqPaySettingsAdminForm(forms.ModelForm):
    class Meta:
        model = LiqPaySettings
        fields = ('public_key', 'private_key')
        widgets = {
            'private_key': forms.PasswordInput(render_value=True),
        }


class LiqPaySettingsAdmin(admin.ModelAdmin):
    form = LiqPaySettingsAdminForm
    list_display = ['public_key']

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return LiqPaySettings.objects.count() == 0

    def has_change_permission(self, request, obj=None):
        return True


admin.site.register(Payment, PaymentAdmin)
admin.site.register(LiqPaySettings, LiqPaySettingsAdmin)
