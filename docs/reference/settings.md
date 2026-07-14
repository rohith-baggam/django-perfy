# Settings reference

Every key `PERFORMANCE_MONITOR` recognizes. Anything omitted falls back to
the default listed here. Source of truth: `django_perfy/utils.py`'s
`_DEFAULTS` dict.

## Core

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `ENABLED` | bool | `True` | Master switch. When `False`, middleware, mixin, snapshots and aggregation all no-op. |
| `SAMPLING_RATE` | float | `0.1` | Fraction (0.0–1.0) of *normal* requests to record. Slow or error responses are always recorded. |
| `SLOW_REQUEST_THRESHOLD_MS` | int | `500` | Requests at or above this always get captured regardless of sampling. |
| `EXCLUDED_PATHS` | list[str] | `["/health/", "/metrics/", "/favicon.ico"]` | Path prefixes the middleware skips entirely. |
| `USER_ID_SALT` | str | `"changeme-in-prod"` | HMAC salt for hashing user ids. Set a real secret in production. |
| `SERVER_IP` | str \| `None` | `None` | Recorded on every captured row as `server_ip`. Auto-detected from the host when left blank — set explicitly if auto-detection picks the wrong interface (e.g. behind Docker/NAT). |

## Retention

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `RETENTION_DAYS_RAW` | int | `30` | Age after which raw API/WebSocket rows are purged. |
| `RETENTION_DAYS_RESOURCES` | int | `90` | Age after which resource snapshots are purged. |

Purging is not automatic — see [Celery setup](../guides/celery-setup.md) for
scheduling `purge_old_logs`.

## Services and resources

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `QUEUE_NAME` | str | `"performance_logs"` | Celery queue used for performance tasks. |
| `ENABLE_PARTITIONING` | bool | `False` | Reserved for table-partitioning strategies. |
| `RESOURCE_SNAPSHOT_INTERVAL_MINUTES` | int | `15` | How often the web process snapshots its own resources (via the built-in fallback timer — see [Celery setup](../guides/celery-setup.md)). |
| `SERVICES` | list[dict] | `[]` | Declared services to monitor. Each dict needs `type` (`web`, `celery_worker`, `celery_beat`, `redis`, `postgres`, `system`) and `name`. See [Configuration](../configuration.md#services). |
| `MONITOR_POSTGRES` | bool | `True` | Collect Postgres metrics in resource snapshots. |
| `MONITOR_REDIS` | bool | `True` | Collect Redis metrics in resource snapshots. |

## Database

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `DATABASE` | str | `"default"` | DB alias every performance model reads from and writes to. See [Secondary database](../guides/secondary-database.md). |

## Header and body capture

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `CAPTURE_HEADERS` | bool | `False` | When `True`, store request/response headers on `APIRequestLog`. Off by default — see [Configuration](../configuration.md#header-and-body-capture). |
| `REDACTED_HEADERS` | list[str] | `["authorization", "cookie", "set-cookie", "x-api-key", "x-auth-token", "proxy-authorization", "x-csrftoken"]` | Header names (case-insensitive) stored as `"[REDACTED]"` instead of their real value when `CAPTURE_HEADERS` is on. |
| `CAPTURE_BODY` | bool | `False` | When `True`, store request/response bodies on `APIRequestLog`. Independent of `CAPTURE_HEADERS` — bodies are higher-sensitivity and higher-volume. Binary content types are recorded as `"[binary omitted]"`. Streaming responses are skipped. |
| `MAX_BODY_BYTES` | int | `8192` | Captured bodies are truncated past this size. |
| `REDACTED_BODY_FIELDS` | list[str] | `["password", "token", "access_token", "refresh_token", "secret", "api_key", "card_number", "cvv", "cvv2", "ssn", "pin"]` | JSON field names (case-insensitive, checked recursively) replaced with `"[REDACTED]"` when a captured body parses as JSON. Non-JSON bodies are captured as truncated raw text with no field-level redaction. |

## Report email

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `EMAIL_ENABLED` | bool | `False` | Opt in to report emailing. |
| `EMAIL_HOST` | str | `""` | Falls back to the project's `EMAIL_HOST` setting if blank. |
| `EMAIL_PORT` | int | `587` | |
| `EMAIL_HOST_USER` | str | `""` | Falls back to the project's `EMAIL_HOST_USER` setting if blank. |
| `EMAIL_HOST_PASSWORD` | str | `""` | Falls back to the project's `EMAIL_HOST_PASSWORD` setting if blank. |
| `EMAIL_USE_TLS` | bool | `True` | |
| `EMAIL_USE_SSL` | bool | `False` | |
| `DEFAULT_FROM_EMAIL` | str | `""` | Falls back to the project's `DEFAULT_FROM_EMAIL`, then `EMAIL_HOST_USER`, if blank. |

Full resolution order and behavior on misconfiguration:
[Emailing reports](../guides/email.md).

## System checks

`manage.py check` validates `PERFORMANCE_MONITOR` if it's present in
settings: `ENABLED`, `SAMPLING_RATE`, `SLOW_REQUEST_THRESHOLD_MS`,
`EXCLUDED_PATHS`, `RETENTION_DAYS_RAW`, `RETENTION_DAYS_RESOURCES`,
`QUEUE_NAME`, `USER_ID_SALT` and `SERVICES` are required keys with type
checks (`performance.E001`/`E002`); `SAMPLING_RATE` must be between 0.0 and
1.0 (`performance.E003`); each `SERVICES` entry needs a valid `type`
(`performance.E005`) and non-empty `name` (`performance.E006`).
