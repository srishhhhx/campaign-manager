"""
Celery application configuration.

The beat_schedule here serves as a fallback; the DatabaseScheduler
used in production will override/extend it via the django_celery_beat tables.
"""

import os
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("core")

# Read Celery config from Django settings, namespace CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """Register the daily campaign send schedule via Celery Beat."""
    from celery.schedules import crontab

    sender.add_periodic_task(
        crontab(hour=settings.CAMPAIGN_SEND_HOUR, minute=0),
        # Import path resolved at runtime to avoid circular imports
        app.signature("campaigns.tasks.send_scheduled_campaigns"),
        name="daily-campaign-send",
    )
