# Getting started

## Install

```bash
pip install django-perfy            # core: middleware, mixin, models, tasks
pip install "django-perfy[reports]" # + dashboard & PDF reports (Jinja2, WeasyPrint)
```

!!! note "Full install details"
    Extras, the WeasyPrint system libraries, static-file serving under
    gunicorn, and the secondary-database migration step are covered on the
    [Installation](installation.md) page. This page is the condensed path.

## 1. Add the app

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "django_perfy",
]
```

## 2. Configure it

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

    # Off by default — see the note below.
    "CAPTURE_HEADERS": False,
    "CAPTURE_BODY": False,

    # Store telemetry in the default DB, or point at a secondary alias:
    "DATABASE": "default",
}
```

See the [settings reference](reference/settings.md) for every key.

!!! warning "CAPTURE_HEADERS and CAPTURE_BODY default to off"
    Request/response headers and bodies routinely carry session cookies,
    auth tokens and other PII. Leave both `False` until you've reviewed
    `REDACTED_HEADERS` and `REDACTED_BODY_FIELDS` in the
    [settings reference](reference/settings.md) — turning them on isn't a
    casual flip.

## 3. Add the API middleware

```python
MIDDLEWARE = [
    # ... after AuthenticationMiddleware so request.user is available ...
    "django_perfy.middleware.PerformanceMiddleware",
]
```

## 4. Instrument WebSocket consumers (optional)

```python
from channels.generic.websocket import AsyncWebsocketConsumer
from django_perfy.mixins import WebSocketLoggingMixin

class ChatConsumer(WebSocketLoggingMixin, AsyncWebsocketConsumer):
    ...
```

## 5. Run migrations

```bash
python manage.py migrate
```

!!! tip "Using a secondary database?"
    If `PERFORMANCE_MONITOR["DATABASE"]` points at a secondary alias, the
    package's tables are pinned there and **will not** be created by a plain
    `migrate`. Run the alias explicitly too — it's an easy step to forget:

    ```bash
    python manage.py migrate --database=performance
    ```

    See [Secondary database](guides/secondary-database.md) for the full
    setup.

## 6. Mount the dashboard (optional)

Requires the `reports` extra. See
[Dashboard & reports](features/dashboard-and-reports.md) for the Jinja2
template backend and static-file setup — production app servers
(gunicorn/uWSGI/daphne) need `collectstatic` plus a static-file server, which
`runserver` doesn't require.

```python
# urls.py
urlpatterns += [path("performance/", include("django_perfy.urls"))]
```

## Next steps

- [Configuration](configuration.md) — the full option set, explained
- [API monitoring](features/api-monitoring.md) and
  [WebSocket monitoring](features/websocket-monitoring.md) — what gets
  captured and how sampling works
- [Celery setup](guides/celery-setup.md) — persistence, aggregation and
  retention tasks, and the built-in fallback timer that runs without Beat
