# Celery setup

django-perfy ships Celery tasks for persistence, aggregation, resource
snapshots, retention and report email, all namespaced under
`django_perfy.tasks.*`. Point Celery at your broker and the middleware/mixin
already submit work to it where relevant — but a good part of the dashboard
populates itself even without Celery Beat running, via a built-in fallback
timer. Knowing which is which avoids two failure modes: assuming Beat is
required when it isn't, and assuming the fallback timer covers more than it
does.

## Task reference

| Task | Triggered by |
| --- | --- |
| `persist_api_log` | Fallback path if the middleware's inline thread-pool write fails |
| `persist_websocket_log` | Fallback path for WebSocket event writes |
| `snapshot_process_resources` | Beat schedule (per service) |
| `snapshot_redis_resources` | Beat schedule |
| `snapshot_postgres_resources` | Beat schedule |
| `aggregate_api_logs` / `aggregate_websocket_logs` | Beat schedule, or the built-in fallback timer (minute granularity only) |
| `purge_old_logs` | Beat schedule — nothing purges without this |
| `send_report_email` | On demand, from the `performance/reports/email/` endpoint |
| `performance_pipeline_health_check` | Beat schedule (optional) — caches counts for external health checks |

All tasks respect `QUEUE_NAME` (default `"performance_logs"`) and no-op
immediately if `ENABLED` is `False`.

## The built-in fallback timer

`AppConfig.ready()` starts two daemon `threading.Timer` loops directly in the
web process, so the dashboard has *something* to show even in a project that
hasn't wired up Celery Beat yet:

- **Web resource snapshots** — fires every `RESOURCE_SNAPSHOT_INTERVAL_MINUTES`
  (default 15, first run after a 60s warm-up), calling the same
  `collect_process_metrics` collector the Celery task uses, for the `web`
  service type only.
- **Minute-granularity aggregation** — fires every 2 minutes (first run after
  a 2-minute warm-up), computing `PerformanceSummary` rows at minute
  granularity for both API and WebSocket logs.

Both loops skip themselves entirely during management commands
(`migrate`, `shell`, `test`, `collectstatic`, and similar) so they don't fire
during a deploy step or a test run — they only start in the actual
server process.

!!! note "What the fallback timer does *not* cover"
    It only snapshots the `web` tier and only aggregates at minute
    granularity. Celery worker, Celery beat, Redis and Postgres resource
    snapshots, hour-granularity aggregation, and retention purging all still
    need Beat. A project running only the fallback timer will have a
    populated Overview and API Performance page, but empty Redis/Postgres
    tiles on System Resources and no automatic retention.

## A representative Beat schedule

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "perfy-snapshot-web": {
        "task": "django_perfy.tasks.snapshot_process_resources",
        "schedule": 900.0,  # 15 min — redundant with the fallback timer, harmless (idempotent)
        "args": ("django-web", "web"),
    },
    "perfy-snapshot-celery-worker": {
        "task": "django_perfy.tasks.snapshot_process_resources",
        "schedule": 900.0,
        "args": ("celery-worker", "celery_worker"),
    },
    "perfy-snapshot-redis": {
        "task": "django_perfy.tasks.snapshot_redis_resources",
        "schedule": 900.0,
    },
    "perfy-snapshot-postgres": {
        "task": "django_perfy.tasks.snapshot_postgres_resources",
        "schedule": 900.0,
    },
    "perfy-aggregate-hour": {
        "task": "django_perfy.tasks.aggregate_api_logs",
        "schedule": crontab(minute=1),
        "args": ("hour",),
    },
    "perfy-purge": {
        "task": "django_perfy.tasks.purge_old_logs",
        "schedule": crontab(hour=3, minute=0),
    },
}
```

Match the `args` to the `SERVICES` entries you've declared in
[Configuration](../configuration.md#services) so the dashboard's service
labels line up with what's actually being snapshotted.
