# API performance page

`performance/api-performance/` — a deeper look at request latency and how it
relates to load and database cost, plus a filterable drill-down into individual
requests. Metric definitions live in [Metrics and concepts](concepts.md).

## KPI tiles

The same `build_kpis(since)` tiles as the [Overview](overview.md#kpi-tiles) —
total requests, throughput, within-SLA %, p50/p95/p99, error rate, avg DB
queries, avg response time, DB %, peak concurrency and peak CPU/RAM — scoped to
the selected range.

## Latency trend chart

Request-weighted p50/p95/p99 per summary window (`_latency_series`), the same
series described on the [Overview](overview.md#latency-trend-chart). Use it to
see whether the tail is rising, and pair it with the concurrency chart below to
tell load-driven latency apart from a code regression.

## Latency vs database queries (scatter)

A scatter of up to the 500 most recent requests, plotting response time (x)
against database query count (y), coloured by status code. It exposes the
relationship the aggregates hide:

- Points drifting up-and-right are the classic N+1 signature — more queries,
  more time.
- A high-latency point with a *low* query count is slow for a non-database
  reason (CPU, an external API call, serialization).

Because it plots recent raw rows (not weighted), read it as a shape/correlation
tool, not a volume measure.

## Concurrency over time

Up to 500 recent rows plotting `concurrent_requests` against time. Overlaying
this on the latency trend is the quickest way to answer "is latency rising
because load is rising?". Remember concurrency is
[per-worker](concepts.md#concurrency), not a fleet-wide total.

## Request drill-down table

A paginated table of individual requests (16 per page, newest first) with
filters that compose:

| Filter | Effect |
| --- | --- |
| Search | `endpoint` contains the text |
| Method | exact HTTP method |
| Status | `2xx` (< 400), `4xx` (400–499), `5xx` (≥ 500) |
| Slow | only requests ≥ 500 ms |

Each row shows timestamp, method, endpoint, status, response time, DB query
count, DB time and concurrency. Paging preserves every active filter and the
range in the URL.

### Request detail (headers and body)

When [`CAPTURE_HEADERS` / `CAPTURE_BODY`](../configuration.md#header-and-body-capture)
are enabled, a row expands to show the captured request/response headers and
bodies, plus the `server_ip` that handled it. `server_ip` is always populated;
headers and bodies appear only when capture is on and only for sampled rows.

!!! warning "Headers and bodies are sensitive"
    Both capture options default to off because headers and bodies routinely
    carry session cookies, auth tokens and PII. Values are redacted per
    `REDACTED_HEADERS` / `REDACTED_BODY_FIELDS`, binary bodies are omitted, and
    bodies are truncated to `MAX_BODY_BYTES` — but review those lists before
    enabling capture. See
    [Configuration](../configuration.md#header-and-body-capture).

## Refresh endpoint

`performance/api/api-performance/` returns the page context as JSON for
in-place refresh, behind the staff-only guard.
