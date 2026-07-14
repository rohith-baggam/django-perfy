# Why django-perfy

django-perfy answers one question: when your API is fast in development but
sits behind real production load, is it still fast — and if not, where is the
time going? It captures the telemetry needed to answer that from inside your
existing Django process, and shows it through a dashboard and PDF reports.

<video controls preload="metadata" playsinline style="width:100%;border-radius:8px;margin:1rem 0">
  <source src="../assets/videos/intro.mp4" type="video/mp4">
  Your browser does not support the video tag.
  <a href="../assets/videos/intro.mp4">Download the intro video</a>.
</video>

## What telemetry means here

Telemetry is the measured record of what your application actually did in
production, as opposed to what a test or a profiler says it does in isolation.
django-perfy records four signals, all sampled from the live request and
WebSocket paths:

| Signal | What it answers |
| --- | --- |
| Request latency, status, size | How fast is each endpoint, and how often does it error? |
| Database query count and time | How much of a request's time is spent in the database, and which endpoints are query-heavy? |
| WebSocket event timing | How long do connect, receive and send events take per consumer? |
| Host resource usage | What are CPU, memory, Redis and Postgres doing while that traffic runs? |

Those raw rows are rolled up into per-endpoint minute and hour percentile
summaries (p50/p95/p99, error rate), so the dashboard and reports read
pre-aggregated data instead of scanning raw logs on every page load.

## Why not just Prometheus and Grafana?

Prometheus and Grafana are excellent, and django-perfy is not trying to
replace them for infrastructure-wide observability. The difference is
operational weight. A Prometheus/Grafana setup is a stack you run and maintain:
an exporter in (or beside) your app, a Prometheus server scraping and storing a
time series, a Grafana instance with dashboards, and the alerting glue between
them. That is the right investment when you are monitoring a fleet of services.

django-perfy is aimed at the case where that is more than you want to run to
see how one Django app behaves. It adds no new service to your deployment:

| | django-perfy | Prometheus + Grafana |
| --- | --- | --- |
| Extra services to run | None | Prometheus server, Grafana, usually an exporter |
| Data store | Your existing Django database (or a secondary alias) | A separate time-series database |
| Instrumentation | One middleware and an optional consumer mixin | An exporter and metric definitions you maintain |
| Frontend | Built-in staff-only dashboard | Grafana dashboards you build |
| Turn on / off | `PERFORMANCE_MONITOR["ENABLED"]` | Scrape config and service lifecycle |
| Application-level detail | Per-endpoint DB query counts, slow-request drill-down, request correlation | Whatever your exporter is wired to expose |

!!! note "Complementary, not exclusive"
    Nothing stops you running both. django-perfy gives you
    application-level request and query detail with almost no setup;
    Prometheus/Grafana give you cross-service infrastructure monitoring. Many
    teams start with django-perfy and add Prometheus later when they outgrow a
    single app's view.

## Lightweight by design

- **No extra process.** The middleware, mixin, and a built-in background timer
  run inside the web process you already have. Celery is used when present but
  is not required for the dashboard to populate — see
  [Celery setup](guides/celery-setup.md).
- **No new datastore.** Telemetry is written with the Django ORM to your
  database, or to a [secondary database](guides/secondary-database.md) alias if
  you want to keep the write load off your primary.
- **Sampling built in.** Slow and error requests are always recorded;
  everything else is sampled at a configurable rate, so overhead stays low at
  volume. The dashboard corrects for the sampling at query time, so the numbers
  still reflect true traffic.
- **One switch.** `PERFORMANCE_MONITOR["ENABLED"]` turns the whole system on or
  off; when it is `False`, the middleware, mixin, snapshots and aggregation all
  no-op.

## What it is not

django-perfy is not an APM tracer — it does not produce distributed traces
across services, and it does not instrument arbitrary function calls. It
measures the request/response and WebSocket boundaries, database cost per
request, and host resources. If you need span-level distributed tracing, reach
for a dedicated APM or OpenTelemetry pipeline.

## Where to go next

- [Getting started](getting-started.md) — install to first request.
- [Installation](installation.md) — extras, system libraries, and migrations.
- [Background](background.md) — intro, demo and installation videos.
