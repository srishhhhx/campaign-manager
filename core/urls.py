from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/subscribers/", include("subscribers.urls")),
    path("api/campaigns/", include("campaigns.urls")),
]
