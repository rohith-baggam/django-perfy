# django-perfy

API, WebSocket and server performance monitoring for Django. Point it at a
Django project and get request latency, database query counts, WebSocket
event timing and host resource usage — rolled up into summaries, surfaced
through a built-in dashboard, and exportable as PDF reports.

```python
PERFORMANCE_MONITOR = {
    "ENABLED": True,
    "SAMPLING_RATE": 0.1,
    "SLOW_REQUEST_THRESHOLD_MS": 500,
}
```

Add the middleware, run a migration, and requests start showing up in the
dashboard. No external time-series database, no agent process — the package
stores everything in your existing Django database, or a secondary one if
you'd rather isolate the write load.

## Why

- **You already have the data.** django-perfy captures it from inside the
  request/response cycle and the WebSocket dispatch path — no separate
  instrumentation layer to keep in sync with your code.
- **Sampling is built in.** Slow requests and errors are always recorded;
  everything else is sampled at a configurable rate, so the overhead stays
  low even at volume.
- **Reports, not just charts.** Latency, throughput, bottleneck and
  resource-utilization PDF reports render from the same data the dashboard
  shows, so a report and a live dashboard view never disagree.
- **Isolate the write load.** Point `PERFORMANCE_MONITOR["DATABASE"]` at a
  secondary alias and a bundled router pins every read, write and migration
  for the package's tables there — one setting, no per-query `using()` calls.

## What it captures

| Signal | Source |
| --- | --- |
| API request latency, status, DB query count/time | `PerformanceMiddleware` |
| WebSocket connect/disconnect/send/receive timing | `WebSocketLoggingMixin` |
| CPU, memory, Redis, Postgres utilization | Celery tasks + a built-in background timer |
| Minute/hour rollups (p50/p95/p99, error rate) | `PerformanceSummary` |

## Where to go next

<div class="grid cards" markdown>

- **Why this over Prometheus/Grafana?** See
  [Why django-perfy](why-django-perfy.md) — and watch the intro video.
- **New to django-perfy?** Start with [Getting started](getting-started.md)
  for the install-to-first-request path.
- **Configuring an existing install?** The
  [settings reference](reference/settings.md) documents every
  `PERFORMANCE_MONITOR` key.
- **Storing telemetry separately?** See
  [Secondary database](guides/secondary-database.md).
- **Wiring up the dashboard?** See
  [Dashboard & reports](features/dashboard-and-reports.md).
- **Prefer video?** The [Background](background.md) page has intro, demo and
  installation walkthroughs.

</div>

!!! note "Requirements"
    Python 3.10+, Django 4.2+, Celery 5.2+, Redis and `psutil` (installed
    automatically). The dashboard and PDF reports need the `reports` extra
    (`pip install "django-perfy[reports]"`), which pulls in Jinja2 and
    WeasyPrint — see [Dashboard & reports](features/dashboard-and-reports.md)
    for WeasyPrint's system-library requirements.
