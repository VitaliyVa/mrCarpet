from django.contrib import admin

from .models import ContactRequest, Subscription

# Register your models here.
admin.site.register(ContactRequest)
admin.site.register(Subscription)
