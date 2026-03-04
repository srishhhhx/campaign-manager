"""
Email sender module for campaign dispatch.

By default, sends real emails over SMTP (Mailgun sandbox or any SMTP provider).
Set USE_DUMMY_EMAIL=True in .env to skip SMTP and log a simulated send — useful
for local development when no Mailgun account is configured.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_campaign_email(campaign, subscriber) -> bool:
    """
    Send a campaign email to a single subscriber.

    Args:
        campaign: Campaign model instance
        subscriber: Subscriber model instance

    Returns:
        True on success.

    Raises:
        Exception on SMTP failure (the calling Celery task will retry).
    """
    if settings.USE_DUMMY_EMAIL:
        logger.info(
            f"[DUMMY] Simulated send to {subscriber.email} | "
            f"Campaign: '{campaign.subject}'"
        )
        return True

    # Build unsubscribe URL for the footer
    unsubscribe_url = (
        f"{settings.APP_BASE_URL}/api/subscribers/unsubscribe/"
        f"?email={subscriber.email}"
    )

    # Render the HTML template with campaign context
    html_body = render_to_string(
        "emails/base_email.html",
        {
            "campaign": campaign,
            "subscriber": subscriber,
            "unsubscribe_url": unsubscribe_url,
        },
    )

    # Build MIMEMultipart/alternative — plain text first, HTML second
    # (email clients prefer the last part they can render)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = campaign.subject
    msg["From"] = settings.DEFAULT_FROM_EMAIL
    msg["To"] = subscriber.email
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"

    msg.attach(MIMEText(campaign.plain_text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Send via SMTP
    with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT) as smtp:
        smtp.ehlo()
        if settings.EMAIL_USE_TLS:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        smtp.sendmail(settings.EMAIL_HOST_USER, subscriber.email, msg.as_string())

    logger.info(f"Email sent to {subscriber.email} | Campaign: '{campaign.subject}'")
    return True
