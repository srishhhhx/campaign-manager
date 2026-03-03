from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Subscriber
from .serializers import SubscriberSerializer, UnsubscribeSerializer


class SubscribeView(APIView):
    """
    POST /api/subscribers/
    Add a new subscriber or re-activate an inactive one.

    Error schema:  {"detail": "message"}
    Success schema: {"message": "...", "subscriber": {...}} or serialized subscriber
    """

    def post(self, request):
        email = request.data.get("email", "").lower().strip()
        first_name = request.data.get("first_name", "")

        # Re-subscribe: email exists but is inactive → flip back to active
        existing = Subscriber.objects.filter(email=email).first()
        if existing:
            if existing.status == Subscriber.Status.INACTIVE:
                existing.status = Subscriber.Status.ACTIVE
                existing.first_name = first_name or existing.first_name
                existing.unsubscribed_at = None
                existing.save(update_fields=["status", "first_name", "unsubscribed_at"])
                return Response(
                    {
                        "message": "Re-subscribed successfully.",
                        "subscriber": SubscriberSerializer(existing).data,
                    },
                    status=status.HTTP_200_OK,
                )
            # Already active
            return Response(
                {"detail": "This email is already subscribed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # New subscription
        serializer = SubscriberSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({"detail": list(serializer.errors.values())[0][0]}, status=status.HTTP_400_BAD_REQUEST)


class UnsubscribeView(APIView):
    """
    POST /api/subscribers/unsubscribe/
    Mark a subscriber as inactive.

    Also handles GET /api/subscribers/unsubscribe/?email=...
    so that unsubscribe links in campaign emails work with a single click.

    Error schema:  {"detail": "message"}
    Success schema: {"message": "..."}
    """

    def _unsubscribe(self, email):
        """Shared unsubscribe logic used by both GET and POST."""
        # Validate email format
        serializer = UnsubscribeSerializer(data={"email": email})
        if not serializer.is_valid():
            return Response(
                {"detail": "A valid email address is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]

        # Business logic checks — handled here to control response shape
        try:
            subscriber = Subscriber.objects.get(email=email)
        except Subscriber.DoesNotExist:
            return Response(
                {"detail": "No subscriber found with this email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if subscriber.status == Subscriber.Status.INACTIVE:
            return Response(
                {"detail": "This email is already unsubscribed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subscriber.status = Subscriber.Status.INACTIVE
        subscriber.unsubscribed_at = timezone.now()
        subscriber.save(update_fields=["status", "unsubscribed_at"])
        return Response({"message": "Successfully unsubscribed."}, status=status.HTTP_200_OK)

    def post(self, request):
        email = request.data.get("email", "")
        return self._unsubscribe(email)

    def get(self, request):
        """Handles one-click unsubscribe links from campaign emails."""
        email = request.query_params.get("email", "")
        return self._unsubscribe(email)
