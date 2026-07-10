# django-perfy

**API, WebSocket and server performance monitoring for Django** — with a
built-in admin dashboard, PDF reports, and the option to keep all telemetry in a
separate database.

`django-perfy` captures request latency, database query counts, WebSocket
events and host resource usage (CPU / memory / Redis / Postgres), rolls them up
into summaries, and surfaces everything through a dashboard and downloadable PDF
reports.

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

### 1. Install the app

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "django_perfy",
]
```

### 2. Configure it

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

    # Store telemetry in the default DB, or point at a secondary alias:
    "DATABASE": "default",
}
```

See [docs/configuration.md](docs/configuration.md) for every option.

### 3. Add the API middleware

```python
MIDDLEWARE = [
    # ... after AuthenticationMiddleware so request.user is available ...
    "django_perfy.middleware.PerformanceMiddleware",
]
```

### 4. Instrument WebSocket consumers (optional)

```python
from channels.generic.websocket import AsyncWebsocketConsumer
from django_perfy.mixins import WebSocketLoggingMixin

class ChatConsumer(WebSocketLoggingMixin, AsyncWebsocketConsumer):
    ...
```

### 5. Run migrations

```bash
python manage.py migrate
# If DATABASE points at a secondary alias, migrate that one too:
python manage.py migrate --database=performance
```

### 6. Mount the dashboard (optional)

See [docs/dashboard-and-reports.md](docs/dashboard-and-reports.md) for the
Jinja2 template backend, `STATICFILES_DIRS`, and URL wiring. In short:

```python
import django_perfy

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [django_perfy.DASHBOARD_TEMPLATES_DIR],
        "APP_DIRS": False,
        "OPTIONS": {
            "environment": "django_perfy.dashboard.jinja2_env.make_environment",
        },
    },
    # ... your existing DjangoTemplates backend (APP_DIRS: True) ...
]

STATICFILES_DIRS = [django_perfy.DASHBOARD_STATIC_DIR]
```

```python
# urls.py
urlpatterns += [path("performance/", include("django_perfy.urls"))]
```

## Storing telemetry in a secondary database

Set `PERFORMANCE_MONITOR["DATABASE"]` to any alias declared in `DATABASES`:

```python
DATABASES = {
    "default": {...},
    "performance": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "perf_metrics",
        # ...
    },
}

PERFORMANCE_MONITOR = {"DATABASE": "performance", ...}
```

The bundled `PerformanceRouter` is registered automatically and pins the
`performance` app's reads, writes and migrations to that alias. Full details and
the multi-database migrate/backup workflow are in
[docs/secondary-database.md](docs/secondary-database.md).

## Emailing reports

Report emailing reads SMTP credentials from settings and raises loudly when it
is misconfigured. See [docs/email.md](docs/email.md).

## Celery

The app ships Celery tasks (persistence, aggregation, snapshots, retention,
report email). Point Celery at your broker and, optionally, schedule the
periodic tasks with Celery Beat. The app also runs lightweight background timers
so summaries and web-process snapshots populate even without Beat. Task names are
namespaced under `django_perfy.tasks.*`.

## Management commands

- `python manage.py rebuild_summaries` — recompute `PerformanceSummary` rollups.
- `python manage.py performance_report` — generate a report from the CLI.
- `python manage.py export_resource_snapshots` — export resource snapshots.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,reports]"
pytest
pre-commit install
```

## License

MIT — see [LICENSE](LICENSE).
