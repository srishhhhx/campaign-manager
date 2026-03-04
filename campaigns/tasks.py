"""
Celery tasks for campaign email dispatch.

Architecture:
  dispatch_campaign (producer)
      └─► group of send_email_to_subscriber tasks (consumers, run in parallel)
              └─► chord callback: update_campaign_send_totals

campaign_logs is the source of truth for all send results.
Redis results are transient and used only for chord coordination.
"""

import logging
from celery import shared_task, chord, group
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="campaigns.tasks.dispatch_campaign")
def dispatch_campaign(self, campaign_send_id: int):
    """
    PRODUCER task.
    Loads all pending CampaignLog rows for this send and fans them out
    as individual send_email_to_subscriber tasks via a Celery group+chord.
    """
    from .models import CampaignSend, CampaignLog

    try:
        campaign_send = CampaignSend.objects.select_related("campaign").get(pk=campaign_send_id)
    except CampaignSend.DoesNotExist:
        logger.error(f"CampaignSend #{campaign_send_id} not found. Aborting dispatch.")
        return

    # Collect all pending log IDs for this send's campaign
    log_ids = list(
        CampaignLog.objects.filter(
            campaign=campaign_send.campaign,
            status=CampaignLog.SendStatus.PENDING,
        ).values_list("id", flat=True)
    )

    if not log_ids:
        logger.warning(f"No pending logs found for CampaignSend #{campaign_send_id}. Nothing to dispatch.")
        return

    logger.info(
        f"Dispatching CampaignSend #{campaign_send_id}: "
        f"{len(log_ids)} email(s) to send in parallel."
    )

    # Fan out: one task per subscriber, dispatched in parallel across workers
    task_group = group(send_email_to_subscriber.s(log_id) for log_id in log_ids)

    # Chord: run callback once all tasks complete (success or failure)
    chord(task_group)(
        update_campaign_send_totals.s(campaign_send_id)
    )


@shared_task(
    bind=True,
    name="campaigns.tasks.send_email_to_subscriber",
    max_retries=3,
    default_retry_delay=60,  # 60s between retries
    rate_limit="5/m",  # Mailgun sandbox: 5/min; increase for production
)
def send_email_to_subscriber(self, log_id: int):
    """
    CONSUMER task.
    Sends one campaign email to one subscriber.
    Idempotency: skips if log is not in PENDING state.
    Retries up to 3 times on SMTP failure.
    """
    from .models import CampaignLog
    from .email_sender import send_campaign_email

    try:
        log = CampaignLog.objects.select_related("campaign", "subscriber").get(pk=log_id)
    except CampaignLog.DoesNotExist:
        logger.error(f"CampaignLog #{log_id} not found.")
        return "not_found"

    # Idempotency: another worker may have already processed this
    if log.status != CampaignLog.SendStatus.PENDING:
        logger.info(f"CampaignLog #{log_id} already {log.status}. Skipping.")
        return "skipped"

    # Skip if subscriber unsubscribed between snapshot and execution
    from subscribers.models import Subscriber
    if log.subscriber.status == Subscriber.Status.INACTIVE:
        log.status = CampaignLog.SendStatus.SKIPPED
        log.save(update_fields=["status"])
        logger.info(f"Subscriber {log.subscriber.email} is inactive. Skipped.")
        return "skipped"

    try:
        send_campaign_email(log.campaign, log.subscriber)
        log.status = CampaignLog.SendStatus.SENT
        log.sent_at = timezone.now()
        log.save(update_fields=["status", "sent_at"])
        logger.info(f"Sent to {log.subscriber.email} for campaign '{log.campaign.subject}'")
        return "sent"

    except Exception as exc:
        import smtplib

        # Permanent failure: SMTP 4xx (unauthorized recipient, auth rejected, etc.)
        # These will never succeed on retry — mark failed immediately.
        is_permanent = (
            isinstance(exc, (smtplib.SMTPDataError, smtplib.SMTPRecipientsRefused))
            and hasattr(exc, "smtp_code")
            and 400 <= exc.smtp_code < 500
        )
        if not is_permanent and isinstance(exc, smtplib.SMTPDataError) and exc.args:
            code = exc.args[0] if exc.args else 0
            is_permanent = 400 <= int(code) < 500

        log.status = CampaignLog.SendStatus.FAILED
        log.error_message = str(exc)
        log.save(update_fields=["status", "error_message"])
        logger.error(f"Failed to send to {log.subscriber.email}: {exc}")

        if is_permanent:
            # Don't retry — this address will never be deliverable with current config
            logger.warning(f"Permanent SMTP failure for {log.subscriber.email}. Not retrying.")
            return "failed"

        raise self.retry(exc=exc)


@shared_task(name="campaigns.tasks.update_campaign_send_totals")
def update_campaign_send_totals(results, campaign_send_id: int):
    """
    CHORD CALLBACK.
    Runs after all send_email_to_subscriber tasks finish.
    Counts final statuses from campaign_logs and updates CampaignSend.
    Redis result entries for individual tasks can expire freely after this.
    """
    from .models import CampaignSend, CampaignLog

    try:
        campaign_send = CampaignSend.objects.get(pk=campaign_send_id)
    except CampaignSend.DoesNotExist:
        logger.error(f"CampaignSend #{campaign_send_id} not found in callback.")
        return

    sent_count = CampaignLog.objects.filter(
        campaign=campaign_send.campaign, status=CampaignLog.SendStatus.SENT
    ).count()
    failed_count = CampaignLog.objects.filter(
        campaign=campaign_send.campaign, status=CampaignLog.SendStatus.FAILED
    ).count()

    campaign_send.total_sent = sent_count
    campaign_send.total_failed = failed_count
    campaign_send.completed_at = timezone.now()
    campaign_send.save(update_fields=["total_sent", "total_failed", "completed_at"])

    logger.info(
        f"CampaignSend #{campaign_send_id} complete. "
        f"Sent: {sent_count}, Failed: {failed_count}"
    )


@shared_task(name="campaigns.tasks.send_scheduled_campaigns")
def send_scheduled_campaigns():
    """
    CELERY BEAT task — fires daily at CAMPAIGN_SEND_HOUR.
    Finds all campaigns where published_date <= today with no completed send yet,
    and triggers dispatch for each.
    """
    from django.utils.timezone import now
    from .models import Campaign, CampaignSend, CampaignLog
    from subscribers.models import Subscriber

    today = now().date()
    campaigns_to_send = Campaign.objects.filter(published_date__lte=today).exclude(
        sends__completed_at__isnull=False
    )

    dispatched = 0
    for campaign in campaigns_to_send:
        # Skip if send already in-flight
        if CampaignSend.objects.filter(campaign=campaign, completed_at__isnull=True).exists():
            logger.info(f"Campaign '{campaign.subject}' already has a send in progress. Skipping.")
            continue

        active_ids = list(
            Subscriber.objects.filter(status=Subscriber.Status.ACTIVE).values_list("id", flat=True)
        )
        if not active_ids:
            logger.warning("No active subscribers for scheduled send.")
            continue

        campaign_send = CampaignSend.objects.create(
            campaign=campaign,
            triggered_by=CampaignSend.TriggerType.SCHEDULED,
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
        dispatched += 1
        logger.info(f"Scheduled send triggered for '{campaign.subject}'")

    logger.info(f"Celery Beat: {dispatched} campaign(s) dispatched.")
