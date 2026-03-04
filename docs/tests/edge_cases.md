# Edge Cases Tested

All edge cases below have corresponding automated unit tests in `campaigns/tests/` and `subscribers/tests/`.

---

## Subscriber Edge Cases

| Edge Case | Test | Behaviour |
|---|---|---|
| Duplicate active subscriber | `test_subscribe_duplicate_active` | Returns 400 "Already subscribed" — does not create duplicate row |
| Re-subscribe inactive user | `test_subscribe_reactivates_inactive` | Status reset to active, `unsubscribed_at` cleared, returns 200 |
| Email normalised to lowercase | `test_email_normalised_to_lowercase` | `USER@EXAMPLE.COM` stored as `user@example.com` |
| Email too long (> 254 chars) | `test_email_too_long` | Returns 400 validation error |
| Missing first_name field | `test_subscribe_missing_first_name` | Returns 400 — field is required |
| Empty request body | `test_subscribe_empty_body` | Returns 400 with field-level errors |
| Unsubscribe already inactive user | `test_unsubscribe_already_inactive` | Returns 400 "Already unsubscribed" |
| Unsubscribe non-existent email | `test_unsubscribe_nonexistent_email` | Returns 400 "Subscriber not found" |
| `unsubscribed_at` set on unsubscribe | `test_unsubscribe_sets_unsubscribed_at` | Timestamp written correctly |

---

## Campaign Send Edge Cases

| Edge Case | Test | Behaviour |
|---|---|---|
| Trigger same campaign twice same day | `test_send_duplicate_same_day` | Returns 409 Conflict on second request |
| Trigger same campaign next day | `test_send_allowed_next_day` | Returns 202 — new `CampaignSend` created |
| No active subscribers | `test_send_no_active_subscribers` | Returns 400 "No active subscribers to send to" |
| Campaign with blank subject | `test_send_empty_subject` | Returns 400 validation error |
| Campaign with no HTML content | `test_send_empty_html_content` | Returns 400 validation error |
| Inactive subscribers excluded | `test_send_excludes_inactive_subscribers` | Only active subscribers in CampaignLog snapshot |
| Future-dated campaign | `test_send_future_dated_campaign` | Returns 400 — `published_date > today` |
| Non-existent campaign ID | `test_send_nonexistent_campaign` | Returns 404 |

---

## Task / Celery Edge Cases

| Edge Case | Test | Behaviour |
|---|---|---|
| Log already SENT (retry arrives late) | `test_send_email_task_idempotency` | Task checks status, returns `"skipped"` — no duplicate send |
| Subscriber unsubscribes mid-send | `test_subscriber_unsubscribes_mid_send` | Task re-checks status at execution, marks log `skipped` |
| SMTP failure on send | `test_send_email_task_marks_log_failed_on_error` | Log marked `failed`, error message stored, retry triggered |
| Permanent SMTP 4xx error | `RealEmailSenderTests::test_smtp_failure_raises` | Marked `failed` immediately — no retry (avoids retry storm) |
| Non-existent CampaignLog ID | `test_send_email_nonexistent_log_returns_not_found` | Returns `"not_found"` without crashing |
| Non-existent CampaignSend in dispatch | `test_dispatch_campaign_nonexistent_send_returns_none` | Returns `None` without crashing |
| Non-existent CampaignSend in chord callback | `test_chord_callback_nonexistent_send_returns_none` | Returns `None` without crashing |
| No pending logs in dispatch | `test_dispatch_campaign_no_pending_logs_returns_none` | Returns `None` — skips group creation |

---

## Beat Scheduler Edge Cases

| Edge Case | Test | Behaviour |
|---|---|---|
| Campaign `published_date` in future | `test_send_scheduled_campaigns_skips_future_campaigns` | Skipped — not yet due |
| Campaign already has completed send today | `test_send_scheduled_campaigns_skips_already_completed` | Skipped — 409 guard |
| Campaign send currently in progress | `test_send_scheduled_campaigns_skips_in_flight_send` | Skipped — avoids duplicate dispatch |
| No active subscribers for campaign | `test_send_scheduled_campaigns_skips_when_no_active_subscribers` | Skipped — nothing to send |
| Campaign due today with active subscribers | `test_send_scheduled_campaigns_dispatches_todays_campaign` | Dispatched correctly |

---

## Database-Level Protection

| Constraint | Location | Effect |
|---|---|---|
| `unique_together = ('campaign', 'subscriber')` | `CampaignLog` | Prevents duplicate log rows at DB level, independent of application logic |
| `unique` on `Subscriber.email` | `Subscriber` | Prevents duplicate subscriber rows — `bulk_create(ignore_conflicts=True)` used for safe re-trigger |
