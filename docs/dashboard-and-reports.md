# Dashboard and reports

The dashboard is a staff-only set of pages rendered with a small Jinja2
environment; the reports engine renders latency, throughput, bottlenecks and
resource-utilization documents to HTML (preview) and PDF (download / email).

Both require the `reports` extra:

```bash
pip install "django-perfy[reports]"
```

## Wiring the dashboard

### 1. Jinja2 template backend

The dashboard templates use Jinja2. Add a Jinja2 backend to `TEMPLATES` and
point it at the packaged template directory via the exported path helper. Keep
your existing `DjangoTemplates` backend too — the admin correlation view and
Django admin use it.

```python
import django_perfy

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [django_perfy.DASHBOARD_TEMPLATES_DIR],
        "APP_DIRS": False,
        "OPTIONS": {
            "environment": "django_perfy.dashboard.jinja2_env.make_environment",
            "autoescape": True,
        },
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
```

### 2. Static assets

```python
import django_perfy

STATICFILES_DIRS = [django_perfy.DASHBOARD_STATIC_DIR]
```

Run `collectstatic` as usual for production.

### 3. URLs

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("performance/", include("django_perfy.urls")),
]
```

That mounts:

| Path | View |
| --- | --- |
| `performance/` | Dashboard overview |
| `performance/api-performance/` | API latency & throughput |
| `performance/websocket/` | WebSocket activity |
| `performance/system-resources/` | CPU / memory / Redis / Postgres |
| `performance/database-queries/` | Query hotspots |
| `performance/correlation/` | Cross-signal correlation |
| `performance/raw-logs/` | Raw log explorer |
| `performance/reports/preview/` | Report HTML preview (POST) |
| `performance/reports/download/` | Report PDF download (POST) |
| `performance/reports/email/` | Email a report (POST) |

The dashboard pages are guarded by `staff_member_required`. An admin
"Performance correlation" view is also injected into the Django admin URLs
automatically when the app is installed.

## Reports from the CLI

```bash
python manage.py performance_report
```

## Report types

| Code | Report |
| --- | --- |
| `latency` | Endpoint latency, Apdex, within-SLA, tail spread |
| `throughput` | Request volume and rates |
| `bottlenecks` | Slowest endpoints and query hotspots |
| `resources` | CPU / memory / Redis / Postgres utilization |

Emailing a report is covered in [email.md](email.md).
