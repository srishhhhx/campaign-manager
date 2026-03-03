import datetime
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from subscribers.models import Subscriber


class SubscribeViewTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/subscribers/"
        self.active_subscriber = Subscriber.objects.create(
            email="active@example.com",
            first_name="Active",
            status=Subscriber.Status.ACTIVE,
        )
        self.inactive_subscriber = Subscriber.objects.create(
            email="inactive@example.com",
            first_name="Inactive",
            status=Subscriber.Status.INACTIVE,
        )

    # ── Happy paths ────────────────────────────────────────────────────────────

    def test_subscribe_success(self):
        """New subscriber returns 201 with correct fields."""
        resp = self.client.post(
            self.url,
            {"email": "new@example.com", "first_name": "New"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        for field in ("id", "email", "first_name", "status", "subscribed_at"):
            self.assertIn(field, data, f"Missing field: {field}")
        self.assertEqual(data["email"], "new@example.com")
        self.assertEqual(data["status"], "active")

    def test_subscribe_reactivates_inactive(self):
        """Inactive subscriber re-subscribing returns 200."""
        resp = self.client.post(
            self.url,
            {"email": "inactive@example.com", "first_name": "Inactive"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("Re-subscribed", data["message"])
        self.assertEqual(data["subscriber"]["status"], "active")

    def test_subscribe_clears_unsubscribed_at_on_resubscribe(self):
        """unsubscribed_at is cleared when re-subscribing."""
        from django.utils import timezone
        Subscriber.objects.filter(pk=self.inactive_subscriber.pk).update(
            unsubscribed_at=timezone.now()
        )
        self.client.post(
            self.url,
            {"email": "inactive@example.com", "first_name": "Inactive"},
            format="json",
        )
        self.inactive_subscriber.refresh_from_db()
        self.assertIsNone(self.inactive_subscriber.unsubscribed_at)

    # ── Error paths ────────────────────────────────────────────────────────────

    def test_subscribe_duplicate_active(self):
        """Existing active subscriber returns 400 with detail key."""
        resp = self.client.post(
            self.url,
            {"email": "active@example.com", "first_name": "Active"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("detail", data)
        self.assertIsInstance(data["detail"], str)  # not a list
        self.assertIn("already subscribed", data["detail"])

    def test_subscribe_invalid_email(self):
        resp = self.client.post(
            self.url, {"email": "notanemail", "first_name": "X"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_subscribe_missing_first_name(self):
        resp = self.client.post(
            self.url, {"email": "nofirstname@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_subscribe_missing_email(self):
        resp = self.client.post(self.url, {"first_name": "NoEmail"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_subscribe_empty_body(self):
        resp = self.client.post(self.url, {}, format="json")
        self.assertEqual(resp.status_code, 400)


class UnsubscribeViewTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/subscribers/unsubscribe/"
        self.active_subscriber = Subscriber.objects.create(
            email="active@example.com",
            first_name="Active",
            status=Subscriber.Status.ACTIVE,
        )
        self.inactive_subscriber = Subscriber.objects.create(
            email="inactive@example.com",
            first_name="Inactive",
            status=Subscriber.Status.INACTIVE,
        )

    # ── Happy paths ────────────────────────────────────────────────────────────

    def test_unsubscribe_success(self):
        """Active subscriber returns 200 with message."""
        resp = self.client.post(
            self.url, {"email": "active@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Successfully unsubscribed", resp.json()["message"])

    def test_unsubscribe_sets_status_inactive(self):
        self.client.post(self.url, {"email": "active@example.com"}, format="json")
        self.active_subscriber.refresh_from_db()
        self.assertEqual(self.active_subscriber.status, Subscriber.Status.INACTIVE)

    def test_unsubscribe_sets_unsubscribed_at(self):
        self.client.post(self.url, {"email": "active@example.com"}, format="json")
        self.active_subscriber.refresh_from_db()
        self.assertIsNotNone(self.active_subscriber.unsubscribed_at)

    # ── Error paths ────────────────────────────────────────────────────────────

    def test_unsubscribe_already_inactive(self):
        """Already inactive subscriber returns 400 with string detail."""
        resp = self.client.post(
            self.url, {"email": "inactive@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("detail", data)
        self.assertIsInstance(data["detail"], str)  # must not be a list
        self.assertIn("already unsubscribed", data["detail"])

    def test_unsubscribe_nonexistent_email(self):
        resp = self.client.post(
            self.url, {"email": "ghost@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.json())

    def test_unsubscribe_missing_email(self):
        resp = self.client.post(self.url, {}, format="json")
        self.assertEqual(resp.status_code, 400)
