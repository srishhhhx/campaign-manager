import datetime
from django.test import TestCase
from django.db import IntegrityError
from campaigns.models import Campaign, CampaignSend, CampaignLog
from subscribers.models import Subscriber


def make_campaign(**kwargs):
    defaults = dict(
        subject="Test Subject",
        preview_text="Test Preview",
        article_url="https://example.com",
        html_content="<h1>Test</h1>",
        plain_text_content="Test",
        published_date=datetime.date.today(),
    )
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


class CampaignModelTests(TestCase):

    def test_campaign_created_successfully(self):
        c = make_campaign()
        self.assertEqual(c.subject, "Test Subject")
        self.assertEqual(c.article_url, "https://example.com")

    def test_campaign_str_representation(self):
        c = make_campaign()
        self.assertIn("Test Subject", str(c))
        self.assertIn(str(datetime.date.today()), str(c))

    def test_campaign_ordering(self):
        old = make_campaign(subject="Old", published_date=datetime.date(2024, 1, 1))
        new = make_campaign(subject="New", published_date=datetime.date(2025, 6, 1))
        subjects = list(Campaign.objects.filter(pk__in=[old.pk, new.pk]).values_list("subject", flat=True))
        self.assertEqual(subjects, ["New", "Old"])

    def test_campaign_send_defaults(self):
        c = make_campaign()
        cs = CampaignSend.objects.create(campaign=c, triggered_by=CampaignSend.TriggerType.MANUAL)
        self.assertEqual(cs.total_sent, 0)
        self.assertEqual(cs.total_failed, 0)
        self.assertIsNone(cs.completed_at)

    def test_campaign_log_unique_together(self):
        c = make_campaign()
        sub = Subscriber.objects.create(email="u@example.com", first_name="U")
        CampaignLog.objects.create(campaign=c, subscriber=sub)
        with self.assertRaises(IntegrityError):
            CampaignLog.objects.create(campaign=c, subscriber=sub)

    def test_campaign_log_default_status_pending(self):
        c = make_campaign()
        sub = Subscriber.objects.create(email="u2@example.com", first_name="U2")
        log = CampaignLog.objects.create(campaign=c, subscriber=sub)
        self.assertEqual(log.status, CampaignLog.SendStatus.PENDING)
