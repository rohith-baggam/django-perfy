# Configuration

All configuration lives in a single `PERFORMANCE_MONITOR` dict in your Django
settings. Any key you omit falls back to its default. Django's system-check
framework validates the block on `manage.py check`.

```python
PERFORMANCE_MONITOR = {
    "ENABLED": True,
    "SAMPLING_RATE": 0.1,
    "SLOW_REQUEST_THRESHOLD_MS": 500,
    "EXCLUDED_PATHS": ["/health/", "/metrics/", "/favicon.ico"],
    "RETENTION_DAYS_RAW": 30,
    "RETENTION_DAYS_RESOURCES": 90,
    "QUEUE_NAME": "performance_logs",
    "USER_ID_SALT": "changeme-in-prod",
    "ENABLE_PARTITIONING": False,
    "RESOURCE_SNAPSHOT_INTERVAL_MINUTES": 15,
    "SERVICES": [],
    "MONITOR_POSTGRES": True,
    "MONITOR_REDIS": True,
    "DATABASE": "default",
    "CAPTURE_HEADERS": False,
    "REDACTED_HEADERS": [
        "authorization", "cookie", "set-cookie", "x-api-key",
        "x-auth-token", "proxy-authorization", "x-csrftoken",
    ],
    "CAPTURE_BODY": False,
    "MAX_BODY_BYTES": 8192,
    "REDACTED_BODY_FIELDS": [
        "password", "token", "access_token", "refresh_token", "secret",
        "api_key", "card_number", "cvv", "cvv2", "ssn", "pin",
    ],
    "SERVER_IP": None,

    # Report email — see guides/email.md
    "EMAIL_ENABLED": False,
    "EMAIL_HOST": "",
    "EMAIL_PORT": 587,
    "EMAIL_HOST_USER": "",
    "EMAIL_HOST_PASSWORD": "",
    "EMAIL_USE_TLS": True,
    "EMAIL_USE_SSL": False,
    "DEFAULT_FROM_EMAIL": "",
}
```

Every key, its type, default and full description lives in the
[settings reference](reference/settings.md) — this page covers the parts
that need more than a one-line explanation.

## Header and body capture

`CAPTURE_HEADERS` and `CAPTURE_BODY` both default to `False`. Headers and
bodies routinely carry session cookies, auth tokens, API keys and other PII —
they are opt-in for a reason, not an oversight.

!!! warning "Turning them on"
    If you enable either, review `REDACTED_HEADERS` and
    `REDACTED_BODY_FIELDS` in the same sitting. Both lists are *extended*, not
    replaced, when you set them in `PERFORMANCE_MONITOR` — add your own
    sensitive field names rather than assuming the defaults cover your API.
    Binary content types are recorded as `"[binary omitted]"` regardless of
    the setting, and only sampled requests (per `SAMPLING_RATE` /
    `SLOW_REQUEST_THRESHOLD_MS`) get headers/bodies captured at all, same as
    every other field.

## `SERVICES`

Each entry describes a monitored service and must include a valid `type`
(`web`, `celery_worker`, `celery_beat`, `redis`, `postgres`, `system`) and a
`name`:

```python
"SERVICES": [
    {"type": "web", "name": "django-web"},
    {"type": "celery_worker", "name": "celery-worker-performance-logs"},
    {"type": "postgres", "name": "primary-db"},
],
```

Django's system checks (`performance.E004`–`E006`) reject an unrecognized
`type` or a missing `name` at `manage.py check` time, before anything tries
to use the block at runtime.

## Runtime reloads

`PERFORMANCE_MONITOR` is cached for speed. The cache is cleared automatically
whenever the setting changes (Django's `setting_changed` signal), so
`override_settings` in tests and live settings reloads both take effect
without a restart.

## Where the rest of this lives

- [Settings reference](reference/settings.md) — every key, one row each.
- [Secondary database](guides/secondary-database.md) — the `DATABASE` key,
  in depth.
- [Emailing reports](guides/email.md) — the `EMAIL_*` keys, in depth.
