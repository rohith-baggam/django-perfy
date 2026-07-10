# Emailing reports

`django-perfy` can email a rendered PDF report as an attachment. Delivery is
driven entirely by settings, and — by design — it **raises loudly** rather than
failing silently when it is disabled or misconfigured, so a broken mailer shows
up in your task logs instead of quietly dropping reports.

## Configuration

Credentials come from the `PERFORMANCE_MONITOR` block first, and fall back to
your project's top-level `EMAIL_*` settings when a value is left blank:

```python
PERFORMANCE_MONITOR = {
    # ...
    "EMAIL_ENABLED": True,             # opt in — defaults to False
    "EMAIL_HOST": "smtp.example.com",
    "EMAIL_PORT": 587,
    "EMAIL_HOST_USER": "reports@example.com",
    "EMAIL_HOST_PASSWORD": "app-password",
    "EMAIL_USE_TLS": True,
    "EMAIL_USE_SSL": False,
    "DEFAULT_FROM_EMAIL": "reports@example.com",
}
```

If you already configure Django's standard email settings, you can leave the
`PERFORMANCE_MONITOR` values blank and only set `EMAIL_ENABLED`:

```python
# Project-wide email settings
EMAIL_HOST = "smtp.example.com"
EMAIL_HOST_USER = "reports@example.com"
EMAIL_HOST_PASSWORD = "app-password"
DEFAULT_FROM_EMAIL = "reports@example.com"

PERFORMANCE_MONITOR = {"EMAIL_ENABLED": True, ...}
```

## Resolution order

For each setting, the value is resolved as:

1. `PERFORMANCE_MONITOR["<KEY>"]` if non-empty, else
2. the top-level Django setting of the same name (e.g. `EMAIL_HOST`), else
3. a built-in default.

The sender address defaults to `EMAIL_HOST_USER` if `DEFAULT_FROM_EMAIL` is not
set anywhere.

## Behavior

`django_perfy.email.send_email(...)` raises `EmailNotConfigured` when:

- `EMAIL_ENABLED` is `False`, or
- no SMTP host can be resolved, or
- no sender address can be resolved.

On a real SMTP failure the underlying error propagates (it is not swallowed), so
the `send_report_email` Celery task retries with backoff.

## Sending

Reports are emailed through the `performance/reports/email/` endpoint (which
validates the address and enqueues the `django_perfy.tasks.send_report_email`
task) or by calling the task directly:

```python
from django_perfy.tasks import send_report_email

send_report_email.delay("latency", "24h", "ops@example.com")
```
