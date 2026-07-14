# Metrics and concepts

Every number on the dashboard and in the reports comes from one of four raw
sources — `APIRequestLog`, `WebSocketEventLog`, `SystemResourceSnapshot` and the
rolled-up `PerformanceSummary`. This page defines each metric and shows exactly
how it is calculated, including the thresholds that drive the colour coding.
The per-page guides link back here rather than repeating the definitions.

## Sampling and inverse-probability weighting

This concept underpins almost every count and rate on the dashboard, so it
comes first.

The middleware does not store every request. Two categories are **always**
stored:

- Requests at or above `SLOW_REQUEST_THRESHOLD_MS` (default 500 ms).
- Requests with a 4xx or 5xx status.

Everything else is stored with probability `SAMPLING_RATE` (default 0.1, i.e.
10%). If the dashboard simply counted stored rows, throughput would look ~10x
too low and the error rate would look far too high, because errors are stored
at 100% while normal requests are stored at 10%.

To correct for this, the dashboard weights each stored row by the inverse of
its storage probability — an estimate of how many real requests it represents:

| Stored row | Weight | Meaning |
| --- | --- | --- |
| Slow (≥ threshold) or error (≥ 400) | `1.0` | Stored at 100%, represents itself |
| Normal, sampled | `1 / SAMPLING_RATE` (e.g. `10.0`) | One stored row stands in for ~10 real requests |

Counts, rates and weighted averages sum these weights instead of counting rows.
So "total requests" is an estimate of true traffic, not the stored row count,
and the error rate reflects real proportions.

!!! note "Where this lives in the code"
    The weight is the `_weight()` expression in `dashboard/views.py`;
    `_wmul(field)` is `weight × field`, used for weighted sums like total DB
    time. Set `SAMPLING_RATE` to `1.0` to store everything and make weights
    all `1.0` — useful in staging where volume is low.

## Percentiles: p50, p95, p99

A percentile is the value below which that percentage of requests fall. For
response time:

- **p50** (median) — half of requests were faster than this.
- **p95** — 95% were faster; the slowest 5% were worse. This is the number
  most teams hold themselves to, because it captures the experience of the
  unlucky tail without being dominated by a handful of outliers.
- **p99** — 99% were faster. The worst 1%. Sensitive to rare slow requests,
  which is exactly what makes it a good early-warning signal.

Percentiles describe the tail in a way an average cannot: an endpoint with a
40 ms average can still have a 900 ms p99, and it is that p99 that a user
notices.

### How the dashboard computes them

Percentiles are **not** recomputed from raw rows on every page load. They are
read from `PerformanceSummary`, which stores per-endpoint p50/p95/p99 for each
minute and hour window. Those stored percentiles are produced during
aggregation with a nearest-rank method over the window's sorted response times:

```
index = int(count × percentile / 100)      # capped at count − 1
```

The dashboard then combines the per-endpoint, per-window percentiles into the
single figure shown in the KPI tile using a **request-weighted average** —
each summary row contributes in proportion to its `total_requests`:

```
p95_shown = Σ(row.p95 × row.total_requests) / Σ(row.total_requests)
```

!!! warning "This is a weighted blend, not a global exact percentile"
    Reading pre-aggregated summaries keeps the dashboard fast, at the cost of
    exactness: the displayed p95 is a request-weighted blend of many windows'
    p95 values, not the true p95 of every individual request in the range. It
    tracks the real percentile closely and, crucially, weights busy endpoints
    heavily so a hot endpoint is not averaged away by many quiet ones (which a
    plain `Avg(p95)` would do). For an exact percentile over a narrow window,
    use the raw-logs page.

## SLA and within-SLA %

The SLA (service-level agreement) target is a single latency threshold:
requests faster than it are "within SLA". On the dashboard this threshold is
`SLA_THRESHOLD_MS`, fixed at **300 ms**.

Within-SLA % is the sampling-weighted share of requests under that threshold:

```
within_sla_% = Σ weight[response_time_ms < 300] / Σ weight × 100
```

So an SLA of 98% means an estimated 98% of real requests completed in under
300 ms. The reports use the same 300 ms default (`SLA_MS`), configurable via
`PERFORMANCE_REPORTS`.

## Apdex

Apdex (Application Performance Index) condenses latency into a single 0–1
satisfaction score around a target time **T** (`APDEX_T_MS`, default 300 ms).
Each request is bucketed:

| Bucket | Condition | Counts as |
| --- | --- | --- |
| Satisfied | `response_time ≤ T` | 1.0 |
| Tolerating | `T < response_time ≤ 4T` | 0.5 |
| Frustrated | `response_time > 4T` | 0.0 |

```
Apdex = (satisfied + tolerating / 2) / total        # sampling-weighted
```

The score is colour-coded in the reports: **≥ 0.94 green**, **≥ 0.85 amber**,
otherwise **red**. Apdex appears in the latency report; the dashboard leads
with raw percentiles and within-SLA instead.

## Error rate

The sampling-weighted share of requests with a 4xx or 5xx status:

```
error_rate_% = Σ weight[status ≥ 400] / Σ weight × 100
```

Because errors are force-stored at 100% and weighted at 1.0, this reflects the
true proportion rather than the inflated raw-row proportion. A separate
non-weighted error **count** is also shown for the raw number of stored error
rows.

## Throughput

Estimated real traffic volume over the selected range, expressed per minute:

```
total_requests   = Σ weight                          # estimated true volume
throughput_rpm   = total_requests / window_seconds × 60
```

The reports also derive requests-per-second (`rpm / 60`) and a peak rate from
the busiest time bucket.

## Concurrency

`concurrent_requests` is recorded per request from a thread-local counter the
middleware increments when a request starts and decrements when it finishes.
The dashboard shows the **peak** (`Max(concurrent_requests)`); the throughput
report also derives mean and p95.

!!! note "Per-process, not global"
    The counter is local to one worker process, so concurrency is a
    same-process approximation — it does not sum across gunicorn/uvicorn
    workers or hosts. Read it as "how loaded was a single worker", not "total
    in-flight requests across the fleet".

## Database cost: query count, DB time, DB %

For the duration of each request the middleware wraps the database connection
with Django's `execute_wrapper`, so it counts **every** query the request
triggers — including queries inside third-party code, not just the ORM calls
django-perfy knows about — and sums their execution time.

| Metric | Meaning |
| --- | --- |
| `db_query_count` | Number of queries the request ran |
| `db_time_ms` | Total time spent in the database |
| DB % | `avg_db_time / avg_response_time × 100` — how much of a request's wall-clock time is database-bound |

A high DB % points at a database-bound endpoint (optimise queries); a low DB %
on a slow endpoint points at CPU or external calls instead.

### DB offenders

Ranking endpoints by average DB time per request hides cheap-but-constant
offenders. The dashboard instead ranks by **estimated total DB time**, which
folds in volume:

```
est_total_db_ms = Σ (weight × db_time_ms)            # per endpoint
share_pct       = est_total_db_ms / Σ est_total_db_ms × 100
```

This surfaces where fixing queries actually pays off most across the whole
range.

## Resource metrics

`SystemResourceSnapshot` rows carry CPU, memory, disk and per-service fields.
Two points matter for reading them:

- **CPU is normalised by logical core count.** A process saturating two cores
  on a four-core host reads as **50%, not 200%** — this matches how
  Prometheus/node_exporter-style tools report process CPU, and keeps the
  0–100% scale meaningful.
- **Peaks vs means.** KPI tiles show the peak CPU/RAM over the range
  (`Max(...)`), because the worst moment is what threatens capacity; trend
  charts show the full series so you can see whether a peak was sustained or a
  spike.

## Scale recommendations (server health scaling)

The Overview page turns the KPIs into three plain-language recommendations —
API, Server and Database — each shown green, amber or red. These are not
machine-learning predictions; they are threshold bands applied to the range's
KPIs, so the logic is fully transparent and lives in `_scale_recommendations`.

### API

Driven by p99 latency and peak concurrency:

| Colour | Condition | Recommendation |
| --- | --- | --- |
| Red | `p99 > 500 ms` or `peak_concurrency > 50` | Scale Now |
| Amber | `p99 > 250 ms` or `peak_concurrency > 30` | Monitor |
| Green | otherwise | Healthy |

(The recommendation text is driven by p99 alone: `> 500` Scale Now, `> 250`
Monitor, else Healthy.)

### Server

Driven by peak CPU and peak RAM:

| Colour | Condition | Recommendation |
| --- | --- | --- |
| Red | `peak_cpu > 80%` or `peak_ram > 85%` | Scale Server |
| Amber | `peak_cpu > 60%` or `peak_ram > 70%` | Monitor |
| Green | otherwise | Healthy |

### Database

Driven by average queries per request and DB %:

| Colour | Condition | Recommendation |
| --- | --- | --- |
| Red | `avg_queries > 10` or `DB% > 50` | Optimize Queries |
| Amber | `avg_queries > 6` | Monitor |
| Green | otherwise | Healthy |

!!! tip "Tuning the bands"
    The dashboard bands are constants in `dashboard/views.py`. The reports read
    the equivalent thresholds from `PERFORMANCE_REPORTS` (`P99_AMBER_MS`,
    `P99_RED_MS`, `CPU_WARN_PCT`, `CPU_CRIT_PCT`, `RAM_WARN_PCT`,
    `RAM_CRIT_PCT`, `DBQ_AMBER`, `DBQ_RED`, `DB_TIME_PCT_RED`), so a report and
    the dashboard agree on what "amber" means. See
    [Report metrics](reports.md).

## User hash

Authenticated requests store an HMAC-SHA256 hash of the user id (salted with
`USER_ID_SALT`), never the raw id. It lets you tell "the same user" apart
across rows without putting identifiable user data in the telemetry tables.

## The time range selector

Every page takes a `range` (1h, 6h, 24h, 7d, 30d). It sets the lower bound
`since` for all queries on the page. Ranges of 6h or less bucket trend charts
by minute; larger ranges bucket by hour. The reports use the same ranges plus
`all`, and read minute-granularity summaries for 1h/6h and hour-granularity for
everything larger.
