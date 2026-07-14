# Database queries page

`performance/database-queries/` — where database cost concentrates and which
endpoints are query-heavy or database-bound. See
[Database cost](concepts.md#database-cost-query-count-db-time-db) for how query
count, DB time and DB % are measured.

## KPI tiles

The `build_kpis(since)` tiles, with the database ones most relevant here: avg DB
queries per request, avg response time, avg DB time and DB %.

## Endpoint DB cost table

One row per endpoint (paginated, 20 per page), sorted by average queries
descending:

| Column | Source |
| --- | --- |
| Avg queries | `Avg(db_query_count)` |
| Max queries | `Max(db_query_count)` |
| Avg DB time | `Avg(db_time_ms)` |
| Max DB time | `Max(db_time_ms)` |
| DB % | `avg_db_ms / avg_response_ms × 100` |

DB % is the tell: a high value means the endpoint's time is dominated by the
database, so query optimisation will move the needle; a low value means the
latency is elsewhere.

## Query-count histogram

Up to 5,000 recent `db_query_count` values bucketed into 12 bins from 0 to the
maximum observed. A long right tail, or a spike at a high bin, points at
endpoints issuing far more queries than typical — usually an N+1 pattern.

## DB time vs response time (scatter)

Up to 500 recent requests plotting `db_time_ms` (x) against `response_time_ms`
(y). Points near the diagonal are database-bound (most of their time is
queries); points well above it spend their time outside the database.

## Slow requests

The 12 slowest requests in the range (`response_time_ms ≥ 500`, ordered
descending), each with its endpoint, response time, query count, DB time,
concurrency and a computed DB % for the individual request. This is the
"show me the worst offenders right now" list.

## DB offenders

Endpoints ranked by **estimated total DB time contribution**, not average per
request — see
[DB offenders](concepts.md#db-offenders). The ranking is
`Σ(weight × db_time_ms)` per endpoint with a `share_pct` of the grand total, so
a cheap-but-constant endpoint that runs millions of times surfaces above a slow
endpoint that runs rarely. This is the list to work down when you want the
largest total database saving.

## Refresh endpoint

`performance/api/db-queries/` returns the page context as JSON, staff-only.
