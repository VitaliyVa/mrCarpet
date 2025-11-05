from django.contrib import admin
from .models import Payment

# Register your models here.
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'status', 'created']
    list_filter = ['status']
    search_fields = ['cart__id']

admin.site.register(Payment)
