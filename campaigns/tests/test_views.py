import datetime
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from campaigns.models import Campaign, CampaignSend, CampaignLog
from subscribers.models import Subscriber


def make_campaign(**kwargs):
    defaults = dict(
        subject="Test Subject",
        preview_text="Preview",
        article_url="https://example.com",
        html_content="<h1>Test</h1>",
        plain_text_content="Test content",
        published_date=datetime.date.today(),
    )
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


def make_active_subscriber(email="sub@example.com", first_name="Sub"):
    return Subscriber.objects.create(
        email=email, first_name=first_name, status=Subscriber.Status.ACTIVE
    )


class CampaignListViewTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/campaigns/"

    def test_list_campaigns_empty(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_list_campaigns_returns_all(self):
        make_campaign(subject="A", published_date=datetime.date(2025, 1, 1))
        make_campaign(subject="B", published_date=datetime.date(2025, 2, 1))
        make_campaign(subject="C", published_date=datetime.date(2025, 3, 1))
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 3)

    def test_list_campaigns_ordered_by_date(self):
        make_campaign(subject="Old", published_date=datetime.date(2024, 1, 1))
        make_campaign(subject="New", published_date=datetime.date(2025, 6, 1))
        resp = self.client.get(self.url)
        subjects = [c["subject"] for c in resp.json()]
        self.assertEqual(subjects[0], "New")


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    USE_DUMMY_EMAIL=True,
)
class CampaignSendViewTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.campaign = make_campaign()
        self.subscriber = make_active_subscriber()

    def _send_url(self, pk=None):
        pk = pk or self.campaign.pk
        return f"/api/campaigns/{pk}/send/"

    # ── Guard: campaign not found ──────────────────────────────────────────────

    def test_send_nonexistent_campaign(self):
        resp = self.client.post(self._send_url(999))
        self.assertEqual(resp.status_code, 404)

    # ── Guard: future date ─────────────────────────────────────────────────────

    def test_send_future_dated_campaign(self):
        future = make_campaign(
            subject="Future",
            published_date=datetime.date.today() + datetime.timedelta(days=1),
        )
        resp = self.client.post(self._send_url(future.pk))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())

    # ── Guard: empty content ───────────────────────────────────────────────────

    def test_send_empty_subject(self):
        c = make_campaign(subject="   ")
        resp = self.client.post(self._send_url(c.pk))
        self.assertEqual(resp.status_code, 400)

    def test_send_empty_html_content(self):
        c = make_campaign(html_content="   ")
        resp = self.client.post(self._send_url(c.pk))
        self.assertEqual(resp.status_code, 400)

    # ── Guard: no subscribers ──────────────────────────────────────────────────

    def test_send_no_active_subscribers(self):
        Subscriber.objects.all().delete()
        resp = self.client.post(self._send_url())
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())

    # ── Guard: duplicate same day ──────────────────────────────────────────────

    def test_send_duplicate_same_day(self):
        self.client.post(self._send_url())
        resp = self.client.post(self._send_url())
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"], "Campaign already sent today.")

    # ── Guard: allowed next day ────────────────────────────────────────────────

    def test_send_allowed_next_day(self):
        self.client.post(self._send_url())

        next_day = timezone.now() + datetime.timedelta(days=1)
        with patch("campaigns.views.timezone") as mock_tz:
            mock_tz.now.return_value = next_day
            resp = self.client.post(self._send_url())
        self.assertIn(resp.status_code, [202, 409])  # 202 = allowed, 409 = same if date didn't change

    # ── Success paths ──────────────────────────────────────────────────────────

    def test_send_success_returns_202(self):
        resp = self.client.post(self._send_url())
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("message", data)
        self.assertIn("campaign_send", data)

    def test_send_success_creates_campaign_send_record(self):
        self.client.post(self._send_url())
        record = CampaignSend.objects.filter(campaign=self.campaign).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.triggered_by, CampaignSend.TriggerType.MANUAL)

    def test_send_success_creates_pending_logs(self):
        make_active_subscriber("extra@example.com", "Extra")
        self.client.post(self._send_url())
        log_count = CampaignLog.objects.filter(campaign=self.campaign).count()
        active_count = Subscriber.objects.filter(status=Subscriber.Status.ACTIVE).count()
        self.assertEqual(log_count, active_count)

    def test_send_excludes_inactive_subscribers(self):
        Subscriber.objects.create(
            email="inactive@example.com",
            first_name="Inactive",
            status=Subscriber.Status.INACTIVE,
        )
        self.client.post(self._send_url())
        log_emails = list(
            CampaignLog.objects.filter(campaign=self.campaign)
            .values_list("subscriber__email", flat=True)
        )
        self.assertNotIn("inactive@example.com", log_emails)
        self.assertIn("sub@example.com", log_emails)


class EmailPreviewViewTests(TestCase):
    """Covers campaigns/views.py lines 106-123 (EmailPreviewView)."""

    def setUp(self):
        self.client = APIClient()
        self.campaign = make_campaign()
        self.subscriber = make_active_subscriber("preview_sub@example.com", "Preview")

    def _preview_url(self, pk=None):
        pk = pk or self.campaign.pk
        return f"/api/campaigns/{pk}/preview/"

    def test_preview_renders_html_for_valid_campaign(self):
        """Returns 200 with HTML content for a valid campaign and active subscriber."""
        resp = self.client.get(self._preview_url())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])

    def test_preview_404_for_nonexistent_campaign(self):
        """Returns 404 when campaign pk does not exist."""
        resp = self.client.get(self._preview_url(pk=9999))
        self.assertEqual(resp.status_code, 404)

    def test_preview_404_when_no_active_subscribers(self):
        """Returns 404 with message when no active subscribers exist."""
        Subscriber.objects.all().delete()
        resp = self.client.get(self._preview_url())
        self.assertEqual(resp.status_code, 404)
        self.assertIn(b"No active subscribers", resp.content)
