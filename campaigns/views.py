from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from subscribers.models import Subscriber
from .models import Campaign, CampaignSend, CampaignLog
from .serializers import CampaignSerializer, CampaignSendSerializer


class CampaignListView(APIView):
    """GET /api/campaigns/"""

    def get(self, request):
        campaigns = Campaign.objects.all()
        serializer = CampaignSerializer(campaigns, many=True)
        return Response(serializer.data)


class CampaignSendView(APIView):
    """
    POST /api/campaigns/{id}/send/
    Triggers a parallel email dispatch for the given campaign.
    Returns 202 Accepted immediately; the actual sends happen asynchronously.
    """

    def post(self, request, pk):
        # 1. Fetch campaign
        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist:
            return Response({"detail": "Campaign not found."}, status=status.HTTP_404_NOT_FOUND)

        # 2. Guard: future-dated campaigns cannot be sent yet
        if campaign.published_date > timezone.now().date():
            return Response(
                {"detail": "Campaign published_date is in the future. Cannot send yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Guard: must have content
        if not campaign.html_content.strip() or not campaign.subject.strip():
            return Response(
                {"detail": "Campaign must have a subject and html_content before sending."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Idempotency: block any send for the same campaign on the same calendar day
        already_sent_today = CampaignSend.objects.filter(
            campaign=campaign,
            triggered_at__date=timezone.now().date(),
        ).exists()
        if already_sent_today:
            return Response(
                {"detail": "Campaign already sent today."},
                status=status.HTTP_409_CONFLICT,
            )

        # 5. Snapshot active subscribers at this moment (list, not lazy queryset)
        active_subscriber_ids = list(
            Subscriber.objects.filter(status=Subscriber.Status.ACTIVE).values_list("id", flat=True)
        )
        if not active_subscriber_ids:
            return Response(
                {"detail": "No active subscribers to send to."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 6. Create CampaignSend record
        campaign_send = CampaignSend.objects.create(
            campaign=campaign,
            triggered_by=CampaignSend.TriggerType.MANUAL,
        )

        # 7. Bulk-create CampaignLog rows (pending) for idempotent per-task checks
        logs = [
            CampaignLog(campaign=campaign, subscriber_id=sub_id, status=CampaignLog.SendStatus.PENDING)
            for sub_id in active_subscriber_ids
        ]
        CampaignLog.objects.bulk_create(logs, ignore_conflicts=True)

        # 8. Fire async Celery task — returns immediately
        from .tasks import dispatch_campaign
        dispatch_campaign.delay(campaign_send.id)

        return Response(
            {
                "message": f"Campaign send started for {len(active_subscriber_ids)} subscriber(s).",
                "campaign_send": CampaignSendSerializer(campaign_send).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class EmailPreviewView(APIView):
    """
    GET /api/campaigns/<pk>/preview/
    Renders the HTML email template in the browser using real DB data.
    Temporary dev-only view — remove before production.
    """

    def get(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        subscriber = Subscriber.objects.filter(status=Subscriber.Status.ACTIVE).first()
        if not subscriber:
            return HttpResponse("No active subscribers found.", status=404)

        unsubscribe_url = (
            f"{request.build_absolute_uri('/api/subscribers/unsubscribe/')}"
            f"?email={subscriber.email}"
        )
        html = render_to_string(
            "emails/base_email.html",
            {
                "campaign": campaign,
                "subscriber": subscriber,
                "unsubscribe_url": unsubscribe_url,
            },
        )
        return HttpResponse(html)
