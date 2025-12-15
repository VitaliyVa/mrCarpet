from django.contrib import admin
from .models import Payment

# Register your models here.
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'status', 'amount', 'currency', 'timestamp']
    list_filter = ['status', 'currency', 'timestamp']
    search_fields = ['order__order_number', 'order__id', 'status']
    readonly_fields = ['timestamp']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('order')

admin.site.register(Payment, PaymentAdmin)
