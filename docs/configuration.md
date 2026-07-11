# Configuration

All configuration lives in a single `PERFORMANCE_MONITOR` dict in your Django
settings. Any key you omit falls back to the default shown below. Django's
system-check framework validates the block on `manage.py check`.

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

    # Report email (see docs/email.md)
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

## Options

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `ENABLED` | bool | `True` | Master switch. When `False`, middleware, mixin, snapshots and aggregation all no-op. |
| `SAMPLING_RATE` | float | `0.1` | Fraction (0.0–1.0) of *normal* requests to record. Slow or error responses are always recorded. |
| `SLOW_REQUEST_THRESHOLD_MS` | int | `500` | Requests at or above this always get captured regardless of sampling. |
| `EXCLUDED_PATHS` | list[str] | health/metrics/favicon | Path prefixes the middleware skips entirely. |
| `RETENTION_DAYS_RAW` | int | `30` | Age after which raw API/WebSocket rows are purged. |
| `RETENTION_DAYS_RESOURCES` | int | `90` | Age after which resource snapshots are purged. |
| `QUEUE_NAME` | str | `"performance_logs"` | Celery queue used for performance tasks. |
| `USER_ID_SALT` | str | `"changeme-in-prod"` | HMAC salt for hashing user ids. Set a real secret in production. |
| `ENABLE_PARTITIONING` | bool | `False` | Reserved for table-partitioning strategies. |
| `RESOURCE_SNAPSHOT_INTERVAL_MINUTES` | int | `15` | How often the web process snapshots its own resources. |
| `SERVICES` | list[dict] | `[]` | Declared services to monitor. Each dict needs `type` and `name`. |
| `MONITOR_POSTGRES` | bool | `True` | Collect Postgres metrics in resource snapshots. |
| `MONITOR_REDIS` | bool | `True` | Collect Redis metrics in resource snapshots. |
| `DATABASE` | str | `"default"` | DB alias every performance model reads from and writes to. See [docs/secondary-database.md](secondary-database.md). |
| `CAPTURE_HEADERS` | bool | `False` | When `True`, store request/response headers on `APIRequestLog` (`request_headers`/`response_headers`). Off by default — headers routinely carry session cookies and auth tokens. Only sampled requests (per `SAMPLING_RATE`/`SLOW_REQUEST_THRESHOLD_MS`) get headers captured, same as every other field. |
| `REDACTED_HEADERS` | list[str] | auth/cookie/api-key names | Header names (case-insensitive) stored as `"[REDACTED]"` instead of their real value when `CAPTURE_HEADERS` is on. |
| `CAPTURE_BODY` | bool | `False` | When `True`, store request/response bodies on `APIRequestLog` (`request_body`/`response_body`). Independent of `CAPTURE_HEADERS` — bodies are higher-sensitivity and higher-volume. Binary content types (images, PDFs, `multipart/form-data`, ...) are recorded as `"[binary omitted]"` instead of raw bytes. Streaming responses are skipped. |
| `MAX_BODY_BYTES` | int | `8192` | Captured bodies are truncated past this size. |
| `REDACTED_BODY_FIELDS` | list[str] | password/token/secret/... | JSON field names (case-insensitive, checked recursively) replaced with `"[REDACTED]"` when a captured body parses as JSON. Non-JSON bodies (form-encoded, HTML) are captured as truncated raw text with no field-level redaction. |
| `SERVER_IP` | str \| `None` | `None` | Recorded on every captured row as `server_ip`. Auto-detected from the host (`socket.gethostbyname(socket.gethostname())`) when left blank — set explicitly if auto-detection picks the wrong interface (e.g. behind Docker/NAT). |
| Email keys | | | See [docs/email.md](email.md). |

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

## Runtime reloads

`PERFORMANCE_MONITOR` is cached for speed. The cache is cleared automatically
whenever the setting changes (Django's `setting_changed` signal), so
`override_settings` in tests and live settings reloads both take effect without
a restart.
