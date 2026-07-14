# Reading the dashboard

The dashboard is a staff-only set of pages that turn the raw telemetry into
KPIs, trend charts and drill-down tables. This section documents every page and
every component on it: what each one shows, and how the number behind it is
calculated. If a term like p95, SLA, Apdex or "scale recommendation" is
unfamiliar, start with [Metrics and concepts](concepts.md) — every page here
links back to it rather than repeating the definitions.

For how to install and wire up the dashboard (Jinja2 backend, static files,
URLs), see [Dashboard & reports](../features/dashboard-and-reports.md). This
section is about *reading* it, not setting it up.

## How data reaches the dashboard

Understanding the pipeline explains why some tiles are exact and others are
estimates, and why a brand-new install shows partial data at first.

```
request / websocket event
        │
        ▼
APIRequestLog / WebSocketEventLog        ← raw rows, sampled (see Sampling)
        │
        ├──────────────► dashboard reads raw rows directly
        │                 (scatter plots, drill-down tables, DB cost)
        ▼
PerformanceSummary                        ← minute/hour rollups: p50/p95/p99,
        │                                    counts, errors, per endpoint
        └──────────────► dashboard reads summaries
                          (KPI percentiles, latency trend, top endpoints)

SystemResourceSnapshot                    ← periodic CPU/RAM/Redis/Postgres
        └──────────────► resources & correlation pages
```

- **Raw rows** are sampled and force-store slow/error requests, so counts and
  rates off them are corrected with [inverse-probability
  weights](concepts.md#sampling-and-inverse-probability-weighting).
- **Summaries** are computed every 2 minutes (minute granularity) by a built-in
  timer, and hourly by Celery Beat if scheduled. Percentile tiles read these,
  so on a fresh install the percentile charts populate a couple of minutes
  after the first traffic. See [Celery setup](../guides/celery-setup.md).
- **Resource snapshots** land every 15 minutes for the web tier via the
  built-in timer; other tiers need Beat.

## Common controls

Every page shares two controls:

- **Time range** — `1h`, `6h`, `24h`, `7d`, `30d`. Sets the lower bound for
  every query on the page and the bucket size for trend charts (minute buckets
  at 6h or less, hour buckets beyond). See
  [the range selector](concepts.md#the-time-range-selector).
- **Auto-refreshing JSON endpoints** — each page has a matching
  `…/api/<page>/` endpoint returning the same context as JSON, used to refresh
  charts without a full reload. They carry the same staff-only guard.

Every page and endpoint is protected by `staff_member_required` — non-staff
users are redirected to the admin login.

## The pages

| Page | What it answers |
| --- | --- |
| [Overview](overview.md) | Is the system healthy right now, and what should I scale? |
| [API performance](api-performance.md) | How does latency relate to load and database cost? |
| [WebSocket](websocket.md) | Are connections, events and broadcasts healthy per consumer? |
| [System resources](system-resources.md) | What are CPU, memory, Redis and Postgres doing per tier? |
| [Database queries](database-queries.md) | Which endpoints are query-heavy or database-bound? |
| [Correlation](correlation.md) | Did a latency spike line up with a resource spike? |
| [Raw logs](raw-logs.md) | The unaggregated rows, filterable, for a specific investigation. |

The PDF reports render from the same data with some added scoring — see
[Report metrics](reports.md).
