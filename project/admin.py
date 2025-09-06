from django.contrib import admin

from .models import ContactRequest, Subscription, SMTPSettings

# Register your models here.
admin.site.register(ContactRequest)
admin.site.register(Subscription)


class SMTPSettingsAdmin(admin.ModelAdmin):
    list_display = ['port', 'host', 'server_email', 'email_host_password']

    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_add_permission(self, request, obj=None):
        return SMTPSettings.objects.count() == 0
    
    def has_change_permission(self, request, obj=None):
        return True

admin.site.register(SMTPSettings, SMTPSettingsAdmin)