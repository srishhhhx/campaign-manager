# Campaign API

## GET `/api/campaigns/`

List all campaigns ordered by `published_date` descending.

### Response — 200 OK

```json
[
    {
        "id": 3,
        "subject": "Never Miss a Trademark Infringement Again",
        "preview_text": "MikeTM Watch scans all 45 trademark classes every week.",
        "published_date": "2026-03-01",
        "article_url": "https://mikelegal.com/TMWatch"
    },
    {
        "id": 2,
        "subject": "MikeLegal Weekly: AI Tools for IP Lawyers",
        "preview_text": "This week: how AI is reshaping IP litigation.",
        "published_date": "2026-02-22",
        "article_url": "https://mikelegal.com/blog/ai-tools"
    }
]
```

---

## POST `/api/campaigns/{id}/send/`

Trigger an asynchronous bulk send for a campaign to all active subscribers.

The response is returned **immediately** — emails dispatch in the background via Celery workers. `total_sent` starts at 0 and is updated by the chord callback once all tasks complete.

### Responses

**202 Accepted** — send started
```json
{
    "message": "Campaign send started for 25 subscriber(s).",
    "campaign_send": {
        "id": 8,
        "campaign": 3,
        "triggered_by": "manual",
        "triggered_at": "2026-03-04T07:41:20.230387Z",
        "total_sent": 0,
        "total_failed": 0,
        "completed_at": null
    }
}
```

**409 Conflict** — campaign already sent today
```json
{
    "error": "Campaign already sent today."
}
```

**400 Bad Request** — no active subscribers
```json
{
    "error": "No active subscribers to send to."
}
```

**400 Bad Request** — campaign has no content
```json
{
    "error": "Campaign has no HTML content."
}
```

**404 Not Found** — campaign does not exist
```json
{
    "detail": "Not found."
}
```

---

## GET `/api/campaigns/{id}/preview/`

Renders the HTML email template for the given campaign using the first active subscriber as context. Returns raw HTML — open directly in a browser to preview the email design before sending.

### Response — 200 OK

Raw HTML — renders the full email template with real campaign content.

**404 Not Found** — if no active subscribers exist or campaign does not exist.
