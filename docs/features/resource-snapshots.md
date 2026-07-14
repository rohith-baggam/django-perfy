# Resource snapshots & rollups

Two independent mechanisms keep the dashboard populated: periodic resource
snapshots (CPU, memory, Redis, Postgres) and rolling percentile summaries
computed from the raw API/WebSocket logs. Both work with Celery Beat, and
both also run without it via a built-in fallback timer — see
[Celery setup](../guides/celery-setup.md) for how the two coexist.

## Resource snapshots

`SystemResourceSnapshot` rows come from three collectors, one per service
type:

| Collector | Service type | Fields |
| --- | --- | --- |
| `collect_process_metrics` | `web`, `celery_worker`, `celery_beat` | CPU%, RAM used/total, disk used/total, open file descriptors, active threads, and (for Celery services) active/queued/reserved task counts |
| `collect_redis_metrics` | `redis` | Used memory, connected clients, blocked clients |
| `collect_postgres_metrics` | `postgres` | Active/idle connections, database size |

CPU percent is normalized by logical core count, so a process saturating two
cores on a four-core host reads as 50%, not 200% — this matches how
Prometheus/node_exporter-style tools report process CPU, rather than
`psutil`'s raw per-core-relative figure.

The web process snapshots itself every `RESOURCE_SNAPSHOT_INTERVAL_MINUTES`
(default 15) via the built-in timer described below. Celery worker, beat,
Redis and Postgres snapshots are Celery tasks — schedule them with Beat if
you want those tiers populated.

## Rollups

`PerformanceSummary` stores minute and hour rollups (total requests, average
response time, p50/p95/p99, error count) per endpoint or consumer, computed
from `APIRequestLog` and `WebSocketEventLog` by `aggregate_api_logs` /
`aggregate_websocket_logs`. The dashboard reads from these summaries for
percentile charts rather than computing percentiles from raw rows on every
page load.

Aggregation is idempotent — it's an `update_or_create` keyed on
`(log_type, endpoint_or_consumer, granularity, window_start)` — so it's safe
for both the built-in timer and a Beat-scheduled task to run for overlapping
windows without producing duplicate or conflicting rows.

## Retention

`purge_old_logs` deletes rows older than `RETENTION_DAYS_RAW` (API/WebSocket
logs) and `RETENTION_DAYS_RESOURCES` (resource snapshots), in batches of
1000, via a Celery task. Nothing purges automatically without scheduling this
task — see [Celery setup](../guides/celery-setup.md).

## Rebuilding rollups

If you change retention or need to regenerate summaries after a gap:

```bash
python manage.py rebuild_summaries
```

See [Management commands](../reference/management-commands.md).
