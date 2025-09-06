from django.contrib import admin

from .models import Settlement, Warehouse, NovaPoshtaSettings

# Register your models here.
admin.site.register(Settlement)
admin.site.register(Warehouse)


class NovaPoshtaSettingsAdmin(admin.ModelAdmin):
    list_display = ['api_key']

    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_add_permission(self, request, obj=None):
        return NovaPoshtaSettings.objects.count() == 0
    
    def has_change_permission(self, request, obj=None):
        return True

admin.site.register(NovaPoshtaSettings, NovaPoshtaSettingsAdmin)
