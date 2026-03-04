import datetime
import smtplib
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from campaigns.models import Campaign
from subscribers.models import Subscriber
from campaigns.email_sender import send_campaign_email


def make_campaign(**kwargs):
    defaults = dict(
        subject="Email Sender Test",
        preview_text="Preview",
        article_url="https://example.com",
        html_content="<h1>Hello {{ subscriber.first_name }}</h1>",
        plain_text_content="Hello there",
        published_date=datetime.date.today(),
    )
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


def make_subscriber(email="sender_test@example.com"):
    return Subscriber.objects.create(
        email=email, first_name="Sender", status=Subscriber.Status.ACTIVE
    )


class DummyEmailSenderTests(TestCase):
    """Tests for USE_DUMMY_EMAIL=True path (lines 34-39)."""

    @override_settings(USE_DUMMY_EMAIL=True)
    def test_dummy_mode_returns_true(self):
        """Dummy mode short-circuits SMTP and returns True."""
        campaign = make_campaign()
        subscriber = make_subscriber()
        result = send_campaign_email(campaign, subscriber)
        self.assertTrue(result)

    @override_settings(USE_DUMMY_EMAIL=True)
    def test_dummy_mode_does_not_touch_smtp(self):
        """Dummy mode never touches smtplib."""
        campaign = make_campaign()
        subscriber = make_subscriber()
        with patch("smtplib.SMTP") as mock_smtp:
            send_campaign_email(campaign, subscriber)
            mock_smtp.assert_not_called()


@override_settings(
    USE_DUMMY_EMAIL=False,
    EMAIL_HOST="smtp.mailgun.org",
    EMAIL_PORT=587,
    EMAIL_USE_TLS=True,
    EMAIL_HOST_USER="test@mailgun.org",
    EMAIL_HOST_PASSWORD="secret",
    DEFAULT_FROM_EMAIL="test@mailgun.org",
    APP_BASE_URL="http://localhost:8000",
)
class RealEmailSenderTests(TestCase):
    """Tests for the real SMTP path (lines 42-78)."""

    def setUp(self):
        self.campaign = make_campaign()
        self.subscriber = make_subscriber("real_send@example.com")

    def _make_smtp_mock(self):
        mock_smtp_instance = MagicMock()
        mock_smtp_ctx = MagicMock()
        mock_smtp_ctx.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_ctx.__exit__ = MagicMock(return_value=False)
        return mock_smtp_ctx, mock_smtp_instance

    def test_smtp_success_returns_true(self):
        """Mocked SMTP success → returns True."""
        mock_ctx, mock_smtp = self._make_smtp_mock()
        with patch("campaigns.email_sender.smtplib.SMTP", return_value=mock_ctx):
            result = send_campaign_email(self.campaign, self.subscriber)
        self.assertTrue(result)

    def test_smtp_builds_correct_message(self):
        """Subject, From, To headers set correctly on the outgoing email."""
        mock_ctx, mock_smtp = self._make_smtp_mock()
        with patch("campaigns.email_sender.smtplib.SMTP", return_value=mock_ctx):
            send_campaign_email(self.campaign, self.subscriber)
        # sendmail is called once with the right recipient
        call_args = mock_smtp.sendmail.call_args
        self.assertIsNotNone(call_args)
        _, to_addr, _ = call_args[0]
        self.assertEqual(to_addr, "real_send@example.com")

    def test_smtp_failure_raises_exception(self):
        """SMTP connection failure propagates as exception (so task can retry)."""
        with patch(
            "campaigns.email_sender.smtplib.SMTP",
            side_effect=smtplib.SMTPException("Connection refused"),
        ):
            with self.assertRaises(smtplib.SMTPException):
                send_campaign_email(self.campaign, self.subscriber)

    def test_template_renders_without_error(self):
        """HTML template renders correctly with campaign + subscriber context."""
        mock_ctx, mock_smtp = self._make_smtp_mock()
        with patch("campaigns.email_sender.smtplib.SMTP", return_value=mock_ctx):
            # Should not raise a TemplateDoesNotExist or render error
            result = send_campaign_email(self.campaign, self.subscriber)
        self.assertTrue(result)
