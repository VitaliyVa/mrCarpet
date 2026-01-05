from django.contrib import admin
from django.contrib.auth.models import Group
from .models import ContactRequest, Subscription, SMTPSettings

# Register your models here.
class SMTPSettingsAdmin(admin.ModelAdmin):
    list_display = ['port', 'host', 'server_email', 'email_host_password']

    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_add_permission(self, request, obj=None):
        return SMTPSettings.objects.count() == 0
    
    def has_change_permission(self, request, obj=None):
        return True
    

class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'text', 'is_processed', 'created']
    search_fields = ['name', 'email', 'text']
    list_filter = ['created']
    date_hierarchy = 'created'
    ordering = ['-created']
    readonly_fields = ['created', 'email', 'text', 'name']
    
    def has_delete_permission(self, request, obj=None):
        return True
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return True


admin.site.register(SMTPSettings, SMTPSettingsAdmin)
admin.site.register(ContactRequest, ContactRequestAdmin)
admin.site.register(Subscription)
admin.site.unregister(Group)