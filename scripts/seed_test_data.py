"""
Seed script for manual test run.
Creates 10 test subscribers and 1 test campaign.

Run with:
    python seed_test_data.py
"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from subscribers.models import Subscriber
from campaigns.models import Campaign
from django.utils import timezone

# ── Subscribers ────────────────────────────────────────────────
names = [
    ("Alice", "alice@example.com"),
    ("Bob", "bob@example.com"),
    ("Carol", "carol@example.com"),
    ("Dave", "dave@example.com"),
    ("Eve", "eve@example.com"),
    ("Frank", "frank@example.com"),
    ("Grace", "grace@example.com"),
    ("Hank", "hank@example.com"),
    ("Ivy", "ivy@example.com"),
    ("Jack", "jack@example.com"),
]

created = 0
for first_name, email in names:
    _, was_created = Subscriber.objects.get_or_create(
        email=email,
        defaults={"first_name": first_name, "status": "active"},
    )
    if was_created:
        created += 1

print(f"Subscribers: {created} created, {len(names) - created} already existed")
print(f"Total active: {Subscriber.objects.filter(status='active').count()}")

# ── Campaign ───────────────────────────────────────────────────
campaign, was_created = Campaign.objects.get_or_create(
    subject="MikeLegal Weekly: AI in LegalTech",
    defaults={
        "preview_text": "How AI is transforming trademark search and contract review.",
        "article_url": "https://blog.mikelegal.com/ai-in-legaltech",
        "html_content": """
            <h3>AI is Reshaping the Legal Industry</h3>
            <p>From trademark monitoring to contract analysis, AI tools are helping lawyers
            work faster and more accurately than ever before.</p>
            <p>This week we explore how MikeLegal's suite of tools is being used by
            3,500+ legal professionals worldwide.</p>
        """,
        "plain_text_content": (
            "AI is Reshaping the Legal Industry\n\n"
            "From trademark monitoring to contract analysis, AI tools are helping lawyers "
            "work faster and more accurately than ever before.\n\n"
            "Read more at: https://blog.mikelegal.com/ai-in-legaltech"
        ),
        "published_date": timezone.now().date(),
    },
)

status = "created" if was_created else "already exists"
print(f"Campaign '{campaign.subject}' — {status} (id={campaign.id})")
print(f"\nReady to test: POST /api/campaigns/{campaign.id}/send/")
