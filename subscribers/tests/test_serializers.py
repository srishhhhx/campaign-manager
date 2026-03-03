from django.test import TestCase
from subscribers.models import Subscriber
from subscribers.serializers import SubscriberSerializer, UnsubscribeSerializer


class SubscriberSerializerTests(TestCase):

    def test_valid_subscriber_data(self):
        data = {"email": "valid@example.com", "first_name": "Valid"}
        s = SubscriberSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_invalid_email_format(self):
        data = {"email": "notanemail", "first_name": "Test"}
        s = SubscriberSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("email", s.errors)

    def test_missing_email(self):
        data = {"first_name": "Test"}
        s = SubscriberSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("email", s.errors)

    def test_missing_first_name(self):
        data = {"email": "valid@example.com"}
        s = SubscriberSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("first_name", s.errors)

    def test_email_too_long(self):
        long_local = "a" * 250
        data = {"email": f"{long_local}@example.com", "first_name": "Long"}
        s = SubscriberSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("email", s.errors)

    def test_email_normalised_to_lowercase(self):
        """validate_email strips and lowercases the email."""
        data = {"email": "  Upper@Example.COM  ", "first_name": "Test"}
        s = SubscriberSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data["email"], "upper@example.com")


class UnsubscribeSerializerTests(TestCase):

    def test_unsubscribe_serializer_valid(self):
        data = {"email": "valid@example.com"}
        s = UnsubscribeSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_unsubscribe_serializer_missing_email(self):
        s = UnsubscribeSerializer(data={})
        self.assertFalse(s.is_valid())
        self.assertIn("email", s.errors)

    def test_unsubscribe_serializer_invalid_email(self):
        s = UnsubscribeSerializer(data={"email": "notvalid"})
        self.assertFalse(s.is_valid())
        self.assertIn("email", s.errors)

    def test_unsubscribe_serializer_normalises_email(self):
        s = UnsubscribeSerializer(data={"email": "USER@EXAMPLE.COM"})
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data["email"], "user@example.com")
