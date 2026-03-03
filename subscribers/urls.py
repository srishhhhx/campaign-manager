from django.urls import path
from .views import SubscribeView, UnsubscribeView

urlpatterns = [
    path("", SubscribeView.as_view(), name="subscribe"),
    path("unsubscribe/", UnsubscribeView.as_view(), name="unsubscribe"),
]
