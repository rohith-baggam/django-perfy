# System resources page

`performance/system-resources/` — CPU, memory and per-tier metrics from
`SystemResourceSnapshot`. A service selector switches between the `web`,
`celery_worker`, `redis` and `postgres` tiers. See
[Resource metrics](concepts.md#resource-metrics) for how CPU normalisation and
peaks work.

!!! note "Which tiers have data"
    The web tier snapshots itself every `RESOURCE_SNAPSHOT_INTERVAL_MINUTES`
    (default 15) via the built-in timer, so it populates without Celery. The
    Celery worker, Redis and Postgres tiers are populated by Celery tasks — if
    those tiles are empty, schedule the snapshot tasks with Beat. See
    [Celery setup](../guides/celery-setup.md).

## CPU trend

Per-snapshot `cpu_percent` for the web process over the range. CPU is
**normalised by logical core count**, so it reads 0–100% of total host
capacity, not per-core (a process on two of four cores reads 50%, not 200%).

## Memory trend

`ram_percent` over time, with `ram_used_mb` / `ram_total_mb` behind it so you
can see both the percentage and the absolute footprint.

## File descriptors and threads

`open_file_descriptors` and `active_threads` for the web process. A steadily
climbing FD count is a classic leak signature (unclosed sockets/files); thread
count helps spot runaway thread pools.

## CPU heatmap (day × hour)

Average web CPU by weekday and hour of day, over the last 30 days (independent
of the page range). Seven rows (Mon–Sun) × 24 columns, each cell the mean CPU
for that slot. It reveals load *patterns* — nightly batch jobs, weekday peaks,
weekend lulls — that a linear trend flattens out.

## Disk usage

The latest snapshot's `disk_used_gb` / `disk_total_gb` / `disk_percent`. Shown
as the most recent reading rather than a trend, since disk moves slowly.

## Celery tier

For the `celery_worker` tier: active, reserved and queued task counts over
time, plus a peak queued-tasks figure. A queue depth that climbs and does not
drain means workers are saturated. These come from Celery's inspect API during
snapshot collection, so they need the Celery snapshot task scheduled.

## Redis tier

`redis_used_memory_mb`, `redis_connected_clients` and `redis_blocked_clients`
over time, with a peak blocked-clients figure. Blocked clients climbing
indicates contention on blocking operations.

## Postgres tier

`postgres_active_connections` and `postgres_idle_connections` over time, a
database-size trend (`postgres_db_size_mb`), and a connection-pressure figure —
the peak share of active connections out of active + idle. High active pressure
signals the database is a bottleneck for concurrency.

## Refresh endpoint

`performance/api/resources/` returns the page context as JSON, staff-only. The
service selector is passed through as a query parameter.
