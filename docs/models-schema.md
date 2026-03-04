# Models Schema

## subscribers_subscriber

| Field | Type | Constraints |
|---|---|---|
| `id` | BigAutoField | PK |
| `email` | EmailField | Unique, max 254 chars, indexed |
| `first_name` | CharField | max 100 chars |
| `status` | CharField | choices: `active` / `inactive`, default `active` |
| `subscribed_at` | DateTimeField | auto set on creation |
| `unsubscribed_at` | DateTimeField | nullable, set on unsubscribe |

## campaigns_campaign

| Field | Type | Constraints |
|---|---|---|
| `id` | BigAutoField | PK |
| `subject` | CharField | max 200 chars |
| `preview_text` | CharField | max 300 chars |
| `article_url` | URLField | max 500 chars |
| `html_content` | TextField | full HTML body |
| `plain_text_content` | TextField | plain text fallback |
| `published_date` | DateField | campaign go-live date |

## campaigns_campaignsend

| Field | Type | Constraints |
|---|---|---|
| `id` | BigAutoField | PK |
| `campaign` | ForeignKey | -> Campaign, CASCADE |
| `triggered_by` | CharField | choices: `manual` / `scheduled` |
| `triggered_at` | DateTimeField | auto set on creation |
| `total_sent` | IntegerField | default 0, updated by chord callback |
| `total_failed` | IntegerField | default 0, updated by chord callback |
| `completed_at` | DateTimeField | nullable, set when all tasks complete |

## campaigns_campaignlog

| Field | Type | Constraints |
|---|---|---|
| `id` | BigAutoField | PK |
| `campaign` | ForeignKey | -> Campaign, CASCADE |
| `subscriber` | ForeignKey | -> Subscriber, CASCADE |
| `status` | CharField | choices: `pending` / `sent` / `failed` / `skipped` |
| `sent_at` | DateTimeField | nullable |
| `error_message` | TextField | nullable, populated on failure |

`unique_together = ('campaign', 'subscriber')` — prevents duplicate sends at the database level regardless of what happens at the application layer.
