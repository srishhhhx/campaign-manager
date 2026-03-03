from rest_framework import serializers
from .models import Subscriber


class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = ["id", "email", "first_name", "status", "subscribed_at"]
        read_only_fields = ["id", "status", "subscribed_at"]

    def validate_email(self, value):
        return value.lower().strip()


class UnsubscribeSerializer(serializers.Serializer):
    """Validates email format only. Business logic is handled in the view."""
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()
