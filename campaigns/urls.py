from django.urls import path
from .views import CampaignListView, CampaignSendView, EmailPreviewView

urlpatterns = [
    path("", CampaignListView.as_view(), name="campaign-list"),
    path("<int:pk>/send/", CampaignSendView.as_view(), name="campaign-send"),
    path("<int:pk>/preview/", EmailPreviewView.as_view(), name="campaign-preview"),
]
