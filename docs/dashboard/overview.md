# Overview page

`performance/` — the landing page. It answers two questions at a glance: is the
system healthy over the selected range, and what, if anything, should you
scale? Every metric here is defined in [Metrics and concepts](concepts.md); this
page describes the specific components and where each value comes from.

## KPI tiles

The row of headline tiles, all computed by `build_kpis(since)` over the
selected range:

| Tile | Source | Notes |
| --- | --- | --- |
| Total requests | `Σ weight` | Sampling-corrected estimate of true volume, not the stored row count. |
| Throughput (rpm) | `total_requests / window_seconds × 60` | Average requests per minute over the range. |
| Within SLA % | `Σ weight[rt < 300ms] / Σ weight` | Share of requests under the 300 ms [SLA](concepts.md#sla-and-within-sla). |
| p50 / p95 / p99 | request-weighted from `PerformanceSummary` | [Percentiles](concepts.md#percentiles-p50-p95-p99); read from rollups, not raw rows. |
| Error rate % | `Σ weight[status ≥ 400] / Σ weight` | Weighted, so it reflects true proportion. |
| Error count | `Count(status ≥ 400)` | Raw stored error rows (not weighted). |
| Avg DB queries | weighted avg of `db_query_count` | Average queries per request. |
| Avg response time | weighted avg of `response_time_ms` | Mean latency (percentiles tell the tail story better). |
| DB % | `avg_db_time / avg_response_time × 100` | Share of request time spent in the database. |
| Peak concurrency | `Max(concurrent_requests)` | Busiest single-worker moment; [per-process](concepts.md#concurrency). |
| Peak CPU / RAM % | `Max(...)` over web snapshots | Worst resource moment in the range. |

## Scale recommendation cards

Three cards — API, Server, Database — each green, amber or red with a
one-line recommendation. These apply fixed threshold bands to the KPIs above;
the full band tables are in
[Scale recommendations](concepts.md#scale-recommendations-server-health-scaling).
In short:

- **API** — from p99 latency and peak concurrency → Healthy / Monitor / Scale
  Now.
- **Server** — from peak CPU and peak RAM → Healthy / Monitor / Scale Server.
- **Database** — from average queries per request and DB % → Healthy / Monitor
  / Optimize Queries.

They are deliberately transparent: nothing is predicted, each colour is a
direct function of the range's numbers, so you can always trace a red card back
to the KPI that tripped it.

## Latency trend chart

p50/p95/p99 over time, one point per summary window. Each window's percentile
is **request-weighted across endpoints** (`_latency_series`), so a single hot
endpoint is not averaged away into a calm-looking line — the opposite of what a
flat `Avg(p99)` would show. Bucket size follows the range (minute at ≤ 6h, hour
beyond).

## Traffic trend chart

Sampling-corrected throughput per time bucket, alongside error-rate and
within-SLA percentages for the same buckets (`_traffic_series`). Because it is
weighted, the request count reflects estimated real volume, not sampled rows.

## Errors by status

A breakdown of stored error responses grouped by status code
(`_error_by_status`) — 400, 401, 403, 404, 429, 500, 502, 503, 504 and so on.
This is a raw count of stored error rows; since errors are force-stored at
100%, the counts are already complete without weighting.

## Top endpoints

A tabbed, paginated table of endpoints, built from `PerformanceSummary`
(`_top_endpoints`). Three tabs re-sort the same data:

| Tab | Sort key |
| --- | --- |
| Slowest | `Avg(p99_ms)` descending |
| Errored | total `error_count` descending |
| Busy | total `total_requests` descending |

Each row also shows average queries per request (joined from the raw
`APIRequestLog` for that endpoint). Ten endpoints per page, with prev/next
paging that preserves the active tab and range in the URL.

## Refresh endpoint

`performance/api/overview/` returns this page's full context as JSON for
in-place chart refresh, behind the same staff-only guard.
