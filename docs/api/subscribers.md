# Subscriber API

## POST `/api/subscribers/`

Subscribe a new user or re-subscribe a previously inactive one.

### Request Body

```json
{
    "email": "user@example.com",
    "first_name": "Jane"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `email` | string | ✅ | Valid email, max 254 chars, normalised to lowercase |
| `first_name` | string | ✅ | max 100 chars |

### Responses

**201 Created** — new subscriber added
```json
{
    "email": "user@example.com",
    "first_name": "Jane",
    "status": "active",
    "subscribed_at": "2026-03-01T08:00:00Z"
}
```

**200 OK** — previously inactive subscriber re-activated
```json
{
    "email": "user@example.com",
    "first_name": "Jane",
    "status": "active",
    "subscribed_at": "2026-03-01T08:00:00Z"
}
```

**400 Bad Request** — subscriber already active
```json
{
    "error": "Already subscribed."
}
```

**400 Bad Request** — validation failure
```json
{
    "email": ["Enter a valid email address."]
}
```

---

## POST `/api/subscribers/unsubscribe/`

Unsubscribe a user by email address.

### Request Body

```json
{
    "email": "user@example.com"
}
```

### Responses

**200 OK** — successfully unsubscribed
```json
{
    "message": "Successfully unsubscribed user@example.com."
}
```

**400 Bad Request** — email not found
```json
{
    "error": "Subscriber not found."
}
```

**400 Bad Request** — already inactive
```json
{
    "error": "Already unsubscribed."
}
```

---

## GET `/api/subscribers/unsubscribe/?email=...`

One-click unsubscribe link embedded in email footers. Accepts email as a query parameter, unsubscribes the user, and returns a plain confirmation response. Used inside HTML email templates via the `List-Unsubscribe` header.
