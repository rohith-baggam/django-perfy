# django-perfy

**API, WebSocket and server performance monitoring for Django** — with a
built-in admin dashboard, PDF reports, and the option to keep all telemetry in a
separate database.

`django-perfy` captures request latency, database query counts, WebSocket
events and host resource usage (CPU / memory / Redis / Postgres), rolls them up
into summaries, and surfaces everything through a dashboard and downloadable PDF
reports.

📖 **Full documentation: <https://rohith-baggam.github.io/django-perfy/>**

---

## Features

- **API monitoring** — a middleware records endpoint, method, status, response
  time, DB query count and DB time, with configurable sampling.
- **WebSocket monitoring** — a Channels consumer mixin records connect /
  disconnect / send / receive events and timings.
- **Resource snapshots** — periodic CPU, memory, Redis and Postgres metrics via
  Celery tasks and a self-contained background timer (works without Celery Beat).
- **Rollups** — minute/hour `PerformanceSummary` aggregates for fast dashboards.
- **Dashboard** — a staff-only Jinja2 dashboard (overview, API, WebSocket,
  resources, DB queries, correlation, raw logs).
- **PDF reports** — latency, throughput, bottlenecks and resource-utilization
  reports, previewable in-browser, downloadable, or emailable.
- **Secondary database** — point all telemetry at a separate DB alias with one
  setting; the bundled router handles reads, writes and migrations.

## Requirements

- Python 3.10+
- Django 4.2+
- Celery 5.2+, Redis, psutil (installed automatically)
- `jinja2` + `weasyprint` for the dashboard and PDF reports (the `reports`
  extra). WeasyPrint needs system libraries (Pango, Cairo) — see its
  [install docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).

## Installation

```bash
pip install django-perfy            # core
pip install "django-perfy[reports]" # + dashboard & PDF reports
```

## Quickstart

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "django_perfy",
]

MIDDLEWARE = [
    # ... after AuthenticationMiddleware so request.user is available ...
    "django_perfy.middleware.PerformanceMiddleware",
]
```

```bash
python manage.py migrate
```

Instrument WebSocket consumers (optional):

```python
from channels.generic.websocket import AsyncWebsocketConsumer
from django_perfy.mixins import WebSocketLoggingMixin

class ChatConsumer(WebSocketLoggingMixin, AsyncWebsocketConsumer):
    ...
```

Full install steps — extras, WeasyPrint system libraries, the dashboard's
Jinja2 backend and static files, and the secondary-database migration — are in
the [documentation](https://rohith-baggam.github.io/django-perfy/installation/).

## Configuration

All configuration lives in a single `PERFORMANCE_MONITOR` dict. Any key you omit
falls back to its default, and Django's system-check framework validates the
block on `manage.py check`.

```python
PERFORMANCE_MONITOR = {
    "ENABLED": True,
    "SAMPLING_RATE": 0.1,               # sample 10% of normal requests
    "SLOW_REQUEST_THRESHOLD_MS": 500,   # always capture requests slower than this
    "EXCLUDED_PATHS": ["/health/", "/metrics/", "/favicon.ico"],
    "RETENTION_DAYS_RAW": 30,
    "RETENTION_DAYS_RESOURCES": 90,
    "QUEUE_NAME": "performance_logs",
    "USER_ID_SALT": "change-me",        # salts hashed user ids
    "SERVICES": [],

    # Off by default: headers/bodies routinely carry session cookies/auth
    # tokens/PII. See the settings reference for the full redaction options.
    "CAPTURE_HEADERS": False,
    "REDACTED_HEADERS": ["authorization", "cookie", "set-cookie", "x-api-key"],
    "CAPTURE_BODY": False,
    "REDACTED_BODY_FIELDS": ["password", "token", "secret", "card_number"],

    # Store telemetry in the default DB, or point at a secondary alias:
    "DATABASE": "default",
}
```

> **`CAPTURE_HEADERS` and `CAPTURE_BODY` default to `False`** because headers and
> bodies routinely carry session cookies, auth tokens and other PII. Leave both
> off until you've reviewed `REDACTED_HEADERS` and `REDACTED_BODY_FIELDS` —
> turning them on isn't a casual flip.

Every key, its type, default and description is in the
[settings reference](https://rohith-baggam.github.io/django-perfy/reference/settings/),
and the parts that need more explanation are covered under
[Configuration](https://rohith-baggam.github.io/django-perfy/configuration/).

## Documentation

| Topic | Link |
| --- | --- |
| Why django-perfy (vs Prometheus/Grafana) | <https://rohith-baggam.github.io/django-perfy/why-django-perfy/> |
| Getting started | <https://rohith-baggam.github.io/django-perfy/getting-started/> |
| Configuration | <https://rohith-baggam.github.io/django-perfy/configuration/> |
| Dashboard & reports | <https://rohith-baggam.github.io/django-perfy/features/dashboard-and-reports/> |
| Secondary database | <https://rohith-baggam.github.io/django-perfy/guides/secondary-database/> |
| Emailing reports | <https://rohith-baggam.github.io/django-perfy/guides/email/> |
| Celery setup | <https://rohith-baggam.github.io/django-perfy/guides/celery-setup/> |
| Management commands | <https://rohith-baggam.github.io/django-perfy/reference/management-commands/> |
| Intro, demo & installation videos | <https://rohith-baggam.github.io/django-perfy/background/> |

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,reports]"
pytest
pre-commit install
```

## License

MIT — see [LICENSE](LICENSE).
