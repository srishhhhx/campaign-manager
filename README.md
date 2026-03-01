# Email Campaign Manager

A Django + Celery backend for managing newsletter subscribers and dispatching bulk campaign emails in parallel.

Built for MikeLegal's Backend Intern assignment.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Django (Port 8000)                    │
│                                                             │
│  POST /api/campaigns/{id}/send/                             │
│    │  Snapshots active subscribers                          │
│    │  bulk_creates CampaignLog rows (pending)               │
│    │  Creates CampaignSend record                           │
│    └─► dispatch_campaign.delay()  ──────────────────────┐  │
│                                                          │  │
│  GET  /api/campaigns/                                    │  │
│  POST /api/subscribers/                                  │  │
│  POST /api/subscribers/unsubscribe/                      │  │
└──────────────────────────────────────────────────────────┼──┘
                                                           │
                         ┌─────────────────────────────────▼──┐
                         │           Redis (Broker)            │
                         │  Task queue + transient chord state │
                         └──────────────────┬─────────────────┘
                                            │
               ┌────────────────────────────┼──────────────────────────┐
               │        Celery Workers (concurrency=4)                 │
               │                                                        │
               │  dispatch_campaign   ─── group ──►  send_email [1]   │
               │       (producer)             └────►  send_email [2]   │
               │                              └────►  send_email [N]   │
               │                                         (consumers)   │
               │                                              │         │
               │                         chord callback ◄────┘         │
               │                     update_campaign_send_totals        │
               │                    (writes final counts to DB)         │
               └────────────────────────────────────────────────────────┘
                                            │
                         ┌──────────────────▼──────────────────┐
                         │         PostgreSQL                   │
                         │  subscribers  campaigns              │
                         │  campaign_sends  campaign_logs ◄─── source of truth
                         └─────────────────────────────────────┘
                                            │
                         ┌──────────────────▼──────────────────┐
                         │     Mailgun SMTP / Dummy Mode        │
                         └─────────────────────────────────────┘
```

---

## How Parallelisation Works

When a campaign send is triggered, the view **snapshots all active subscriber IDs** into a list and creates a `CampaignLog` row (status: `pending`) for each one. It then fires a single Celery task — `dispatch_campaign` — and returns HTTP 202 immediately.

Inside `dispatch_campaign`, a **Celery `group`** is built: one `send_email_to_subscriber` task per subscriber. The group is wrapped in a **`chord`** so that once all tasks finish (success or failure), a callback (`update_campaign_send_totals`) runs to write final sent/failed counts back to the `CampaignSend` record.

This means **N emails are dispatched simultaneously** across all available Celery worker threads (`--concurrency=4` by default), rather than serially. Each worker task checks the `CampaignLog` for idempotency before sending, so duplicate processing is safe.

**`campaign_logs` is the single source of truth** for send results. Redis only holds transient state needed for chord coordination — those results can expire freely.

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- A `.env` file (copy from `.env.example`)

```bash
cp .env.example .env
# Fill in SECRET_KEY, DB credentials, and optionally Mailgun SMTP.
# Set USE_DUMMY_EMAIL=True to skip real email sending during local dev.
```

### Run

```bash
docker compose up --build
```

This starts 5 services: `db`, `redis`, `django` (auto-migrates on boot), `celery_worker`, `celery_beat`.

### Create superuser

```bash
docker compose exec django python manage.py createsuperuser
```

Then open [http://localhost:8000/admin/](http://localhost:8000/admin/)

---

## API Reference

| Method | Endpoint | Body | Response |
|---|---|---|---|
| `POST` | `/api/subscribers/` | `{"email": "...", "first_name": "..."}` | `201` new subscriber / `200` re-subscribed / `400` already active |
| `POST` | `/api/subscribers/unsubscribe/` | `{"email": "..."}` | `200` unsubscribed / `400` not found or already inactive |
| `GET` | `/api/campaigns/` | — | `200` list of all campaigns |
| `POST` | `/api/campaigns/{id}/send/` | — | `202` send started / `409` in-flight / `400` validation error |

One-click unsubscribe from email links: `GET /api/subscribers/unsubscribe/?email=...`

---

## Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` / `False` |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `APP_BASE_URL` | Base URL used in unsubscribe links |
| `DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT` | PostgreSQL connection |
| `CELERY_BROKER_URL` | Redis URL for task queue (e.g. `redis://redis:6379/0`) |
| `CELERY_RESULT_BACKEND` | Redis URL for chord callbacks (e.g. `redis://redis:6379/1`) |
| `EMAIL_HOST / EMAIL_PORT / EMAIL_USE_TLS` | SMTP server settings |
| `EMAIL_HOST_USER / EMAIL_HOST_PASSWORD` | SMTP credentials (Mailgun sandbox) |
| `DEFAULT_FROM_EMAIL` | Sender name + address |
| `USE_DUMMY_EMAIL` | `True` = skip SMTP, log simulated send |
| `CAMPAIGN_SEND_HOUR` | UTC hour for daily Celery Beat send (default: `8`) |

---

## Testing Parallel Dispatch

1. **Add subscribers** via API or Django admin (add at least 5–10)

2. **Add a campaign** via Django admin with `published_date = today`

3. **Trigger send**:
   ```bash
   curl -X POST http://localhost:8000/api/campaigns/1/send/
   ```

4. **Watch the worker logs** — you'll see multiple `send_email_to_subscriber` tasks fire simultaneously:
   ```bash
   docker compose logs -f celery_worker
   # [INFO] Task send_email_to_subscriber[abc] received
   # [INFO] Task send_email_to_subscriber[def] received  ← same timestamp
   # [INFO] Task send_email_to_subscriber[ghi] received  ← parallel
   ```

5. **Check results** in Django admin under **Campaign Logs** — each row shows `sent` / `failed` / `skipped`. The `CampaignSend` record shows final totals once the chord callback completes.

---

## Design Decisions

- **`campaign_logs` over Redis for results** — Redis holds transient chord state only. Every permanent send outcome is written directly by the Celery task into `CampaignLog`. This makes auditing, retry logic, and idempotency checks DB-native and durable.
- **`chord` over `chain`** — A `chain` would execute tasks serially. A `group` inside a `chord` fans out all tasks in parallel and fires a single callback when done, making it the correct primitive for bulk fan-out.
- **Subscriber snapshot at send time** — Active subscribers are snapped into a list at the moment of dispatch. Mid-send unsubscribes are handled per-task via a re-check before sending.
- **`bulk_create` with `ignore_conflicts=True`** — Makes re-triggering idempotent without a separate existence check per subscriber.

---

## Project Structure

```
├── core/               Django project config, Celery app, root URLs
├── subscribers/        Subscriber model, subscribe/unsubscribe API
├── campaigns/          Campaign models, send API, Celery tasks, email sender
├── templates/emails/   HTML email template (base_email.html)
├── docker-compose.yml  5-service composition
├── Dockerfile          Python 3.11 slim image
├── .env.example        All environment variable docs
└── requirements.txt    Pinned dependencies
```
