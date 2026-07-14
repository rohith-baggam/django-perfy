# Report metrics

The four PDF reports render from the same telemetry as the dashboard and reuse
its sampling-corrected helpers, so a report and a live dashboard view never
disagree on the underlying numbers. On top of that shared data each report adds
its own derived scoring — Apdex gauges, a priority index, severity bands, a
binding constraint, an SLO table. This page defines those.

All thresholds come from `PERFORMANCE_REPORTS` (with the defaults below), so you
can retune them without touching code. The four reports and their codes:

| Report | Code | Focus |
| --- | --- | --- |
| API Latency & Cost | `PTR-LAT` | Per-endpoint latency, Apdex, DB cost, within-SLA |
| Throughput & Capacity | `PTR-THR` | Volume, rates, concurrency, SLOs |
| Resource Utilization | `PTR-RES` | CPU/RAM/Redis/Postgres per tier, binding constraint |
| Bottleneck Analysis | `PTR-BNK` | Ranked root-cause findings |

## Shared basis

Every report is built over a resolved `(start, end)` window from the same
[range keys](concepts.md#the-time-range-selector) as the dashboard, plus `all`
(open lower bound). Numbers are
[sampling-weighted](concepts.md#sampling-and-inverse-probability-weighting) via
the same `_weight()` / `build_kpis()` helpers. Each report has a document id of
the form `CODE-YYYY-MMDD`.

## Latency report (PTR-LAT)

### Apdex gauge

The overall [Apdex](concepts.md#apdex) score, weighted across all requests,
rendered as a ring gauge. `T` is `APDEX_T_MS` (default 300 ms); colour is
**≥ 0.94 green, ≥ 0.85 amber, else red**.

### Within-SLA and tail spread

- **Within SLA %** — weighted share under `SLA_MS` (300 ms).
- **Tail spread** — `p99 / p50` per endpoint. A ratio near 1 is a consistent
  endpoint; a large ratio means a heavy tail (most requests fast, a few very
  slow).

### Priority index

Each endpoint gets a 0–100 priority score blending three normalised factors, so
the report can rank *where to look first* rather than just listing the slowest:

```
raw = 0.30 × (traffic share)
    + 0.35 × (tail severity)          # p95 vs P99_RED_MS (500 ms), clamped
    + 0.35 × (share of total DB time)
priority = raw / max(raw) × 100
```

Weighting volume, tail and database cost together stops a rarely-hit slow
endpoint from outranking a constantly-hit expensive one.

### Per-endpoint columns

Traffic share, weighted requests, p50/p95/p99, avg DB queries, avg DB ms, DB %,
estimated DB ms, compute-hours, DB-hours, egress MB, Apdex and within-SLA — all
weighted, all per endpoint. The bubble chart plots traffic share against p95
with bubble size by DB share, and shades a "fix-first zone" above the SLA line.

## Throughput report (PTR-THR)

### Rates and concurrency

- **Mean / peak RPS** — `throughput_rpm / 60`, and the busiest bucket's rate.
- **Concurrency** — mean, p95 and peak of `concurrent_requests`
  ([per-worker](concepts.md#concurrency)).

### Pool utilisation

Only shown if you set `DB_POOL_SIZE` (default `None`, so it is omitted — the
pool size is not something django-perfy can read). When set:

```
pool_pct = peak_concurrency / DB_POOL_SIZE × 100
```

Colour: red above `POOL_WARN_PCT` (85%), amber above 70%, else green.

### SLO table

Pass/fail rows against fixed objectives:

| Objective | Target |
| --- | --- |
| Success rate | ≥ 99.5% |
| Error rate (4xx+5xx) | < 0.5% |
| Peak concurrency band | ≤ `CONC_AMBER` (30) |
| Peak concurrency vs pool | < `POOL_WARN_PCT` (85%), if pool size set |

An error donut breaks stored errors down by status code.

## Resource report (PTR-RES)

### Per-tier utilisation

For each tier (`web`, `celery_worker`, `redis`, `postgres`) with data: mean and
peak CPU and RAM, sample count, and tier-specific extras (Postgres connections
and size, Redis memory and clients, Celery queue/active, web FDs and threads).

CPU/RAM gauges colour against the configured bands: CPU amber at
`CPU_WARN_PCT` (60), red at `CPU_CRIT_PCT` (80); RAM amber at `RAM_WARN_PCT`
(70), red at `RAM_CRIT_PCT` (85).

### Binding constraint

The report names the single metric closest to (or over) its critical limit —
the resource that will run out first — by comparing each candidate's gap to its
limit:

```
gap = limit − value       # smallest gap wins
near = gap ≤ 5
over = value ≥ limit
```

Candidates are Web CPU (vs `CPU_CRIT_PCT`) and Web RAM (vs `RAM_CRIT_PCT`). The
CPU and RAM trend charts draw the critical threshold as a dashed line.

## Bottleneck report (PTR-BNK)

### Severity bands (P1 / P2 / P3)

Each DB offender is graded from its DB % and average queries per request:

| Level | Condition |
| --- | --- |
| P1 | `DB% > DB_TIME_PCT_RED` (50) **or** `avg_queries > DBQ_RED` (10) |
| P2 | `avg_queries > DBQ_AMBER` (6) |
| P3 | otherwise |

Findings get stable ids (`PTR-BNK-F01`, …) and, if you supply a curated
`BOTTLENECK_STATUS` map, a resolution status column; otherwise the report states
the status is uncurated.

### Findings and matrix

The findings table lists each offender's estimated DB ms, share, avg queries,
DB % and severity. An impact-vs-effort bubble matrix plots average queries (x,
"effort") against share of DB time (y, "impact"), so the top-right bubbles are
the high-impact, high-query targets. The report also carries the same
[scale recommendations](concepts.md#scale-recommendations-server-health-scaling)
as the dashboard and the 12 slowest individual requests.

## Retuning thresholds

Set any of these under `PERFORMANCE_REPORTS` in settings to change the bands
without editing code:

```python
PERFORMANCE_REPORTS = {
    "SLA_MS": 300,
    "APDEX_T_MS": 300,
    "P99_AMBER_MS": 250,
    "P99_RED_MS": 500,
    "CONC_AMBER": 30,
    "CONC_RED": 50,
    "DB_POOL_SIZE": None,      # set to your pool size to show pool utilisation
    "POOL_WARN_PCT": 85,
    "DBQ_AMBER": 6,
    "DBQ_RED": 10,
    "DB_TIME_PCT_RED": 50,
    "CPU_WARN_PCT": 60,
    "CPU_CRIT_PCT": 80,
    "RAM_WARN_PCT": 70,
    "RAM_CRIT_PCT": 85,
    # Masthead / branding and BOTTLENECK_STATUS also live here.
}
```

The defaults mirror the dashboard's own bands so the two never disagree about
what "amber" or "within SLA" means.
