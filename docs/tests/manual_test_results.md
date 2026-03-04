# Manual Test Results

All tests performed against the local dev environment: Django runserver + Celery worker (concurrency=4) + Redis + PostgreSQL.

---

## 1. Subscribe / Unsubscribe Flow

| Test | Command | Expected | Result |
|---|---|---|---|
| Subscribe new user | `POST /api/subscribers/` `{"email":"...", "first_name":"..."}` | 201 + subscriber created | Pass |
| Subscribe same email again (active) | Same request twice | 400 "Already subscribed" | Pass |
| Re-subscribe inactive user | Same email after unsubscribe | 200 + status reset to active | Pass |
| Unsubscribe existing active | `POST /api/subscribers/unsubscribe/` | 200 + status set to inactive | Pass |
| Unsubscribe already inactive | Same request again | 400 "Already unsubscribed" | Pass |
| Unsubscribe unknown email | Non-existent email | 400 "Subscriber not found" | Pass |

---

## 2. Campaign Send — Parallel Dispatch

**Setup:** 25 active subscribers (5 real Gmail addresses + 20 example.com), dummy mode OFF, Mailgun sandbox SMTP.

```bash
curl -s -X POST http://localhost:8000/api/campaigns/3/send/ | python3 -m json.tool
```

**Immediate API response (< 50ms):**
```json
{
    "message": "Campaign send started for 25 subscriber(s).",
    "campaign_send": {
        "id": 7,
        "triggered_by": "manual",
        "triggered_at": "2026-03-03T10:30:25.165319Z",
        "total_sent": 0,
        "total_failed": 0,
        "completed_at": null
    }
}
```

**Worker logs — all 25 tasks received within 250ms:**
```
[07:28:47,160] Dispatching CampaignSend #8: 25 email(s) to send in parallel.
[07:28:47,276] Task send_email_to_subscriber[...] received   ← 20 tasks received
[07:28:47,325] Task send_email_to_subscriber[...] received   ← within 250ms
...
[07:28:50,249] Email sent to srishtikn215@gmail.com
[07:28:50,458] Email sent to nagendra10kasaragod@gmail.com
[07:28:50,638] Email sent to srish18srishan@gmail.com
```

**Chord callback:**
```
CampaignSend #8 complete. Sent: 5, Failed: 20
```
*(20 example.com addresses rejected by Mailgun sandbox — expected)*

---

## 3. Duplicate Send Guard

Triggering the same campaign twice on the same day:

```bash
curl -s -X POST http://localhost:8000/api/campaigns/3/send/ | python3 -m json.tool
```

**Response:**
```json
{
    "error": "Campaign already sent today."
}
```
Status: **409 Conflict**   

---

## 4. Mailgun Real Send (5 recipients)

After deactivating example.com addresses, triggered a clean send to 5 real Gmail addresses.

```
CampaignSend #8 complete. Sent: 5, Failed: 0
```

All 5 Gmail inboxes received the email with:
- Correct subject: "Never Miss a Trademark Infringement Again"
- Rendered HTML template with gradient header
- CTA button linking to `https://mikelegal.com/TMWatch`
- Unsubscribe link in footer

**Result: End-to-end delivery confirmed**

---

## 5. Celery Beat Scheduling

Temporarily changed Beat schedule to `crontab(minute='*/1')` to verify firing:

```
[11:24:00] Scheduler: Sending due task daily-campaign-send (campaigns.tasks.send_scheduled_campaigns)
[11:25:00] Scheduler: Sending due task daily-campaign-send (campaigns.tasks.send_scheduled_campaigns)
```

**Result: Beat fires on schedule, picks up eligible campaigns**

---

## 6. Mid-Send Unsubscribe

Subscriber unsubscribed between snapshot and task execution. Worker log:

```
Subscriber inactive@example.com is inactive. Skipped.
Task send_email_to_subscriber[...] succeeded: 'skipped'
```

**Result: Inactive check in task correctly skips delivery**
