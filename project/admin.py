from django.contrib import admin
from django.contrib.auth.models import Group
from .models import ContactRequest, Subscription, SMTPSettings

# Register your models here.
class SMTPSettingsAdmin(admin.ModelAdmin):
    list_display = ["host", "port", "server_email", "username", "use_tls", "use_ssl"]
    fieldsets = (
        (
            "SMTP (Gmail)",
            {
                "description": (
                    "Для Gmail: Host = smtp.gmail.com, Port = 587, TLS = увімкнено, SSL = вимкнено. "
                    "У полі «Пароль» потрібен App Password (не звичайний пароль акаунта). "
                    "Створити: Google Account → Security → 2-Step Verification → App passwords."
                ),
                "fields": (
                    "host",
                    "port",
                    "server_email",
                    "username",
                    "email_host_password",
                    "use_tls",
                    "use_ssl",
                ),
            },
        ),
    )

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