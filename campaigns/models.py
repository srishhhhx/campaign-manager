from django.db import models


class Campaign(models.Model):
    subject = models.CharField(max_length=200)
    preview_text = models.CharField(max_length=300)
    article_url = models.URLField(max_length=500)
    html_content = models.TextField()
    plain_text_content = models.TextField()
    published_date = models.DateField(db_index=True)

    class Meta:
        ordering = ["-published_date"]
        verbose_name = "Campaign"
        verbose_name_plural = "Campaigns"

    def __str__(self):
        return f"{self.subject} ({self.published_date})"


class CampaignSend(models.Model):
    class TriggerType(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        MANUAL = "manual", "Manual"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="sends")
    triggered_by = models.CharField(max_length=10, choices=TriggerType.choices)
    triggered_at = models.DateTimeField(auto_now_add=True)
    total_sent = models.IntegerField(default=0)
    total_failed = models.IntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-triggered_at"]
        verbose_name = "Campaign Send"
        verbose_name_plural = "Campaign Sends"

    def __str__(self):
        return f"Send #{self.pk} for '{self.campaign.subject}' ({self.triggered_by})"


class CampaignLog(models.Model):
    class SendStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="logs")
    subscriber = models.ForeignKey(
        "subscribers.Subscriber", on_delete=models.CASCADE, related_name="campaign_logs"
    )
    status = models.CharField(max_length=10, choices=SendStatus.choices, default=SendStatus.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        # Prevent sending the same campaign to the same subscriber twice
        unique_together = ("campaign", "subscriber")
        ordering = ["-sent_at"]
        verbose_name = "Campaign Log"
        verbose_name_plural = "Campaign Logs"

    def __str__(self):
        return f"Log [{self.status}] — {self.subscriber.email} | Campaign #{self.campaign_id}"
