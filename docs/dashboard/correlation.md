# Correlation page

`performance/correlation/` — overlays one endpoint's latency against system
resource usage on a shared time axis, so you can see whether a latency spike
lined up with a CPU, memory or Celery-queue spike. This is the page for
answering "why was it slow *then*?".

## Controls

- **Endpoint selector** — the endpoints seen in the range, with static/media
  and asset paths (`.css`, `.js`, `.png`, `.ico`, …) filtered out so the list
  is real application endpoints. Defaults to the first available.
- **Time window** — an explicit `start`/`end` (ISO datetime) window rather than
  a preset range, so you can zoom into the exact incident. If `start` is after
  `end`, it falls back to the page's default range.

## Correlation chart

Four series on one time axis for the selected endpoint and window:

| Series | Source |
| --- | --- |
| p99 latency | `PerformanceSummary.p99_ms` for the endpoint |
| CPU % | web `SystemResourceSnapshot.cpu_percent` |
| RAM % | web `SystemResourceSnapshot.ram_percent` |
| Celery queued | `celery_worker` snapshots' `celery_queued_tasks` |

When the p99 line rises at the same moment as CPU or the Celery queue, the
latency is resource-driven; when p99 rises with flat resources, look at the
code path or an external dependency instead.

!!! note "Snapshot resolution limits correlation"
    Resource snapshots land every 15 minutes by default, so the resource
    series is coarse. For tight correlation, lower
    `RESOURCE_SNAPSHOT_INTERVAL_MINUTES` (and schedule the Celery snapshot
    tasks for non-web tiers) so there are enough points to line up against
    latency.

## Request timeline

The 12 most recent requests to the selected endpoint in the window, with method,
status, response time, DB query count, DB time and concurrency — and the
captured headers/body drawer when
[capture is enabled](../configuration.md#header-and-body-capture). It lets you
drop from "the chart shows a spike here" to the actual requests in that spike.

## Admin correlation view

A parallel, simpler correlation view is injected into the Django admin at
`admin/performance/correlation/` when `django.contrib.admin` is installed. It
takes `endpoint`, `start` and `end` query parameters and lists the matching
API rows next to the resource snapshots for the same window — useful when you
are already in the admin and do not need the full charted page.

## Refresh endpoint

`performance/api/correlation/` returns the page context as JSON, staff-only.
