from django.contrib import admin
from .models import Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "status", "subscribed_at", "unsubscribed_at")
    list_filter = ("status",)
    search_fields = ("email", "first_name")
    readonly_fields = ("subscribed_at", "unsubscribed_at")
    ordering = ("-subscribed_at",)
