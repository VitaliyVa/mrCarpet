from django.contrib import admin

from .models import Order

# Register your models here.
# admin.site.register(Order)


class OrderAdmin(admin.ModelAdmin):
    readonly_fields = ("order_number",)


admin.site.register(Order, OrderAdmin)