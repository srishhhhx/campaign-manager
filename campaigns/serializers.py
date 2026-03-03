from rest_framework import serializers
from .models import Campaign, CampaignSend


class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = [
            "id",
            "subject",
            "preview_text",
            "article_url",
            "html_content",
            "plain_text_content",
            "published_date",
        ]


class CampaignSendSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignSend
        fields = [
            "id",
            "campaign",
            "triggered_by",
            "triggered_at",
            "total_sent",
            "total_failed",
            "completed_at",
        ]
        read_only_fields = fields
