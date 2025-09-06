from django.contrib import admin

from .models import Settlement, Warehouse, NovaPoshtaSettings

# Register your models here.
admin.site.register(Settlement)
admin.site.register(Warehouse)
admin.site.register(NovaPoshtaSettings)