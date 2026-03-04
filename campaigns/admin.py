from django.contrib import admin
from django.utils.html import format_html
from .models import Campaign, CampaignSend, CampaignLog


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("subject", "published_date", "preview_text", "trigger_send_link")
    list_filter = ("published_date",)
    search_fields = ("subject", "preview_text")
    actions = ["trigger_send"]

    @admin.display(description="Actions")
    def trigger_send_link(self, obj):
        return format_html(
            '<a class="button" href="/api/campaigns/{}/send/" '
            'onclick="return confirm(\'Trigger send for this campaign?\')">Trigger Send</a>',
            obj.pk,
        )

    @admin.action(description="Trigger campaign send for selected campaigns")
    def trigger_send(self, request, queryset):
        from django.utils import timezone
        from subscribers.models import Subscriber
        from .models import CampaignSend, CampaignLog
        from .tasks import dispatch_campaign

        triggered = []
        skipped = []

        for campaign in queryset:
            if campaign.published_date > timezone.now().date():
                skipped.append(f"{campaign.subject} (future date)")
                continue

            in_flight = CampaignSend.objects.filter(
                campaign=campaign, completed_at__isnull=True
            ).exists()
            if in_flight:
                skipped.append(f"{campaign.subject} (send in progress)")
                continue

            active_ids = list(
                Subscriber.objects.filter(status=Subscriber.Status.ACTIVE).values_list("id", flat=True)
            )
            if not active_ids:
                skipped.append(f"{campaign.subject} (no active subscribers)")
                continue

            campaign_send = CampaignSend.objects.create(
                campaign=campaign,
                triggered_by=CampaignSend.TriggerType.MANUAL,
            )
            logs = [
                CampaignLog(
                    campaign=campaign,
                    subscriber_id=sub_id,
                    status=CampaignLog.SendStatus.PENDING,
                )
                for sub_id in active_ids
            ]
            CampaignLog.objects.bulk_create(logs, ignore_conflicts=True)
            dispatch_campaign.delay(campaign_send.id)
            triggered.append(campaign.subject)

        if triggered:
            self.message_user(request, f"Triggered send for: {', '.join(triggered)}")
        if skipped:
            self.message_user(request, f"Skipped: {', '.join(skipped)}", level="warning")


@admin.register(CampaignSend)
class CampaignSendAdmin(admin.ModelAdmin):
    list_display = ("campaign", "triggered_by", "triggered_at", "total_sent", "total_failed", "completed_at")
    list_filter = ("triggered_by",)
    readonly_fields = ("campaign", "triggered_by", "triggered_at", "total_sent", "total_failed", "completed_at")


@admin.register(CampaignLog)
class CampaignLogAdmin(admin.ModelAdmin):
    list_display = ("campaign", "subscriber", "status", "sent_at", "error_message")
    list_filter = ("status",)
    search_fields = ("subscriber__email", "campaign__subject")
    readonly_fields = ("campaign", "subscriber", "status", "sent_at", "error_message")
