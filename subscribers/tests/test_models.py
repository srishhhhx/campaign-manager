import datetime
from django.test import TestCase
from django.db import IntegrityError
from django.utils import timezone
from subscribers.models import Subscriber


class SubscriberModelTests(TestCase):

    def setUp(self):
        self.subscriber = Subscriber.objects.create(
            email="model_test@example.com",
            first_name="Model",
        )

    def test_subscriber_created_with_active_status(self):
        """Default status on creation is active."""
        self.assertEqual(self.subscriber.status, Subscriber.Status.ACTIVE)

    def test_subscriber_email_unique(self):
        """Duplicate email raises IntegrityError."""
        with self.assertRaises(IntegrityError):
            Subscriber.objects.create(
                email="model_test@example.com",
                first_name="Duplicate",
            )

    def test_subscriber_unsubscribed_at_null_by_default(self):
        """unsubscribed_at is None on creation."""
        self.assertIsNone(self.subscriber.unsubscribed_at)

    def test_subscriber_str_representation(self):
        """__str__ returns 'FirstName <email> (status)'."""
        expected = f"Model <model_test@example.com> (active)"
        self.assertEqual(str(self.subscriber), expected)

    def test_subscriber_ordering(self):
        """Subscribers ordered by -subscribed_at (newest first)."""
        older = Subscriber.objects.create(email="oldest@example.com", first_name="Oldest")
        newer = Subscriber.objects.create(email="newest@example.com", first_name="Newest")

        # Force different subscribed_at by updating via queryset
        Subscriber.objects.filter(pk=older.pk).update(
            subscribed_at=timezone.now() - datetime.timedelta(days=2)
        )
        Subscriber.objects.filter(pk=newer.pk).update(
            subscribed_at=timezone.now() - datetime.timedelta(days=1)
        )

        emails = list(
            Subscriber.objects.filter(
                pk__in=[older.pk, newer.pk]
            ).values_list("email", flat=True)
        )
        self.assertEqual(emails, ["newest@example.com", "oldest@example.com"])
