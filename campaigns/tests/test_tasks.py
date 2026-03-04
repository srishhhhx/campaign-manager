import datetime
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.utils import timezone
from campaigns.models import Campaign, CampaignSend, CampaignLog
from subscribers.models import Subscriber


def make_campaign(**kwargs):
    defaults = dict(
        subject="Task Test Campaign",
        preview_text="Preview",
        article_url="https://example.com",
        html_content="<h1>Test</h1>",
        plain_text_content="Test content",
        published_date=datetime.date.today(),
    )
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


def make_subscriber(email, status=Subscriber.Status.ACTIVE):
    name = email.split("@")[0].capitalize()
    return Subscriber.objects.create(email=email, first_name=name, status=status)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    USE_DUMMY_EMAIL=True,
)
class DispatchCampaignTaskTests(TestCase):

    def setUp(self):
        self.campaign = make_campaign()
        self.subs = [make_subscriber(f"sub{i}@example.com") for i in range(5)]
        self.campaign_send = CampaignSend.objects.create(
            campaign=self.campaign,
            triggered_by=CampaignSend.TriggerType.MANUAL,
        )
        # Create pending logs for all subscribers
        CampaignLog.objects.bulk_create([
            CampaignLog(
                campaign=self.campaign,
                subscriber=sub,
                status=CampaignLog.SendStatus.PENDING,
            )
            for sub in self.subs
        ])

    def test_dispatch_campaign_sends_to_all_active_subscribers(self):
        """5 active subscribers → all 5 CampaignLog rows updated to sent."""
        from campaigns.tasks import dispatch_campaign
        dispatch_campaign(self.campaign_send.id)

        sent_count = CampaignLog.objects.filter(
            campaign=self.campaign, status=CampaignLog.SendStatus.SENT
        ).count()
        self.assertEqual(sent_count, 5)

    def test_dispatch_campaign_skips_inactive_subscribers(self):
        """Subscriber turned inactive before task runs → log marked skipped."""
        # Make one subscriber inactive mid-send
        inactive_sub = self.subs[0]
        inactive_sub.status = Subscriber.Status.INACTIVE
        inactive_sub.save(update_fields=["status"])

        from campaigns.tasks import dispatch_campaign
        dispatch_campaign(self.campaign_send.id)

        skipped = CampaignLog.objects.get(
            campaign=self.campaign, subscriber=inactive_sub
        )
        self.assertEqual(skipped.status, CampaignLog.SendStatus.SKIPPED)

        sent_count = CampaignLog.objects.filter(
            campaign=self.campaign, status=CampaignLog.SendStatus.SENT
        ).count()
        self.assertEqual(sent_count, 4)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    USE_DUMMY_EMAIL=True,
)
class SendEmailTaskTests(TestCase):

    def setUp(self):
        self.campaign = make_campaign()
        self.subscriber = make_subscriber("tasktest@example.com")
        self.log = CampaignLog.objects.create(
            campaign=self.campaign,
            subscriber=self.subscriber,
            status=CampaignLog.SendStatus.PENDING,
        )

    def test_send_email_task_marks_log_sent(self):
        """Successful send updates CampaignLog to sent and populates sent_at."""
        from campaigns.tasks import send_email_to_subscriber
        send_email_to_subscriber(self.log.id)

        self.log.refresh_from_db()
        self.assertEqual(self.log.status, CampaignLog.SendStatus.SENT)
        self.assertIsNotNone(self.log.sent_at)

    def test_send_email_task_idempotency(self):
        """Log already sent → task returns 'skipped', no duplicate processing."""
        self.log.status = CampaignLog.SendStatus.SENT
        self.log.save(update_fields=["status"])

        from campaigns.tasks import send_email_to_subscriber
        result = send_email_to_subscriber(self.log.id)
        self.assertEqual(result, "skipped")

    def test_send_email_task_marks_log_failed_on_error(self):
        """SMTP failure → log status = failed, error_message populated."""
        with patch(
            "campaigns.email_sender.send_campaign_email",
            side_effect=Exception("SMTP connection refused"),
        ):
            from campaigns.tasks import send_email_to_subscriber
            # With eager propagation, the retry raises the exception — catch it
            try:
                send_email_to_subscriber(self.log.id)
            except Exception:
                pass  # Expected: retry raises after max_retries in eager mode

        self.log.refresh_from_db()
        self.assertEqual(self.log.status, CampaignLog.SendStatus.FAILED)
        self.assertIn("SMTP", self.log.error_message)

    def test_subscriber_unsubscribes_mid_send(self):
        """Subscriber marked inactive after snapshot → log marked skipped."""
        self.subscriber.status = Subscriber.Status.INACTIVE
        self.subscriber.save(update_fields=["status"])

        from campaigns.tasks import send_email_to_subscriber
        result = send_email_to_subscriber(self.log.id)

        self.assertEqual(result, "skipped")
        self.log.refresh_from_db()
        self.assertEqual(self.log.status, CampaignLog.SendStatus.SKIPPED)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    USE_DUMMY_EMAIL=True,
)
class ChordCallbackTests(TestCase):

    def setUp(self):
        self.campaign = make_campaign()
        self.campaign_send = CampaignSend.objects.create(
            campaign=self.campaign,
            triggered_by=CampaignSend.TriggerType.MANUAL,
        )

    def test_chord_callback_updates_totals(self):
        """update_campaign_send_totals sets total_sent and completed_at."""
        subs = [make_subscriber(f"chord{i}@example.com") for i in range(3)]
        for sub in subs:
            CampaignLog.objects.create(
                campaign=self.campaign,
                subscriber=sub,
                status=CampaignLog.SendStatus.SENT,
            )

        from campaigns.tasks import update_campaign_send_totals
        update_campaign_send_totals(["sent", "sent", "sent"], self.campaign_send.id)

        self.campaign_send.refresh_from_db()
        self.assertEqual(self.campaign_send.total_sent, 3)
        self.assertEqual(self.campaign_send.total_failed, 0)
        self.assertIsNotNone(self.campaign_send.completed_at)

    def test_chord_callback_counts_failures(self):
        """Mixed sent/failed results reflected correctly in totals."""
        subs = [make_subscriber(f"mixed{i}@example.com") for i in range(4)]
        statuses = [
            CampaignLog.SendStatus.SENT,
            CampaignLog.SendStatus.SENT,
            CampaignLog.SendStatus.FAILED,
            CampaignLog.SendStatus.FAILED,
        ]
        for sub, st in zip(subs, statuses):
            CampaignLog.objects.create(
                campaign=self.campaign,
                subscriber=sub,
                status=st,
            )

        from campaigns.tasks import update_campaign_send_totals
        update_campaign_send_totals([], self.campaign_send.id)

        self.campaign_send.refresh_from_db()
        self.assertEqual(self.campaign_send.total_sent, 2)
        self.assertEqual(self.campaign_send.total_failed, 2)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    USE_DUMMY_EMAIL=True,
)
class ScheduledCampaignTaskTests(TestCase):
    """Covers campaigns/tasks.py lines 154-194 (send_scheduled_campaigns)."""

    def setUp(self):
        self.subscriber = make_subscriber("sched@example.com")

    def test_send_scheduled_campaigns_dispatches_todays_campaign(self):
        """Campaign published today with no prior send → dispatch triggered."""
        campaign = make_campaign(subject="Today's Campaign", published_date=datetime.date.today())

        from campaigns.tasks import send_scheduled_campaigns
        send_scheduled_campaigns()

        # CampaignSend should have been created with triggered_by=scheduled
        send = CampaignSend.objects.filter(campaign=campaign).first()
        self.assertIsNotNone(send)
        self.assertEqual(send.triggered_by, CampaignSend.TriggerType.SCHEDULED)

    def test_send_scheduled_campaigns_skips_future_campaigns(self):
        """Campaign with future published_date is not dispatched."""
        future_campaign = make_campaign(
            subject="Future Campaign",
            published_date=datetime.date.today() + datetime.timedelta(days=5),
        )

        from campaigns.tasks import send_scheduled_campaigns
        send_scheduled_campaigns()

        send = CampaignSend.objects.filter(campaign=future_campaign).first()
        self.assertIsNone(send)

    def test_send_scheduled_campaigns_skips_already_completed(self):
        """Campaign with a completed send (completed_at set) is excluded."""
        campaign = make_campaign(subject="Already Sent Campaign", published_date=datetime.date.today())
        existing_send = CampaignSend.objects.create(
            campaign=campaign,
            triggered_by=CampaignSend.TriggerType.MANUAL,
            completed_at=timezone.now(),
        )

        from campaigns.tasks import send_scheduled_campaigns
        send_scheduled_campaigns()

        # Only the existing send should exist — no new one created
        total_sends = CampaignSend.objects.filter(campaign=campaign).count()
        self.assertEqual(total_sends, 1)

    def test_send_scheduled_campaigns_skips_in_flight_send(self):
        """Campaign with in-flight send (completed_at=None) is skipped."""
        campaign = make_campaign(subject="In-Flight Campaign", published_date=datetime.date.today())
        CampaignSend.objects.create(
            campaign=campaign,
            triggered_by=CampaignSend.TriggerType.MANUAL,
            # completed_at=None → in-flight
        )

        from campaigns.tasks import send_scheduled_campaigns
        send_scheduled_campaigns()

        total_sends = CampaignSend.objects.filter(campaign=campaign).count()
        self.assertEqual(total_sends, 1)  # No new send created

    def test_send_scheduled_campaigns_skips_when_no_active_subscribers(self):
        """No active subscribers → dispatch skipped, no CampaignSend created."""
        self.subscriber.status = Subscriber.Status.INACTIVE
        self.subscriber.save(update_fields=["status"])

        campaign = make_campaign(subject="No Subs Campaign", published_date=datetime.date.today())

        from campaigns.tasks import send_scheduled_campaigns
        send_scheduled_campaigns()

        send = CampaignSend.objects.filter(campaign=campaign).first()
        self.assertIsNone(send)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    USE_DUMMY_EMAIL=True,
)
class TaskErrorGuardTests(TestCase):
    """Covers the error guard branches in tasks.py (lines 31-33, 80-82, 125-127)."""

    def test_dispatch_campaign_nonexistent_send_returns_none(self):
        """dispatch_campaign with invalid ID returns early without exception."""
        from campaigns.tasks import dispatch_campaign
        result = dispatch_campaign(99999)
        self.assertIsNone(result)

    def test_dispatch_campaign_no_pending_logs_returns_none(self):
        """dispatch_campaign with no PENDING logs returns early."""
        campaign = make_campaign()
        campaign_send = CampaignSend.objects.create(
            campaign=campaign, triggered_by=CampaignSend.TriggerType.MANUAL
        )
        # No logs created — should return early
        from campaigns.tasks import dispatch_campaign
        result = dispatch_campaign(campaign_send.id)
        self.assertIsNone(result)

    def test_send_email_nonexistent_log_returns_not_found(self):
        """send_email_to_subscriber with invalid log ID returns 'not_found'."""
        from campaigns.tasks import send_email_to_subscriber
        result = send_email_to_subscriber(99999)
        self.assertEqual(result, "not_found")

    def test_chord_callback_nonexistent_send_returns_none(self):
        """update_campaign_send_totals with invalid send ID returns early."""
        from campaigns.tasks import update_campaign_send_totals
        result = update_campaign_send_totals([], 99999)
        self.assertIsNone(result)
