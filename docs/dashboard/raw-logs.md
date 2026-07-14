# Raw logs page

`performance/raw-logs/` — the unaggregated rows behind everything else, for
when you need to see specific requests or events rather than a rollup. Two
tables: API requests and WebSocket events, each independently filterable.

## API request logs

The same drill-down as the [API performance
page](api-performance.md#request-drill-down-table) (18 rows per page, newest
first) with the composable filters:

| Filter | Effect |
| --- | --- |
| Search | `endpoint` contains the text |
| Method | exact HTTP method |
| Status | `2xx` / `4xx` / `5xx` |
| Slow | only requests ≥ 500 ms |

Rows carry timestamp, method, endpoint, status, response time, DB query count,
DB time, concurrency and — when
[capture is enabled](../configuration.md#header-and-body-capture) — the
headers/body drawer and `server_ip`.

## WebSocket event logs

Raw `WebSocketEventLog` rows (18 per page, newest first) with two filters:

| Filter | Effect |
| --- | --- |
| Consumer | exact `consumer_name` |
| Event | `connect` / `disconnect` / `receive` / `send` |

Each row shows timestamp, consumer, event type, direction, message size,
processing time and — for disconnects — connection duration.

## What this page is for

Everything else on the dashboard aggregates or samples-corrects the data. This
page shows the stored rows as they are, which is what you want when
reproducing a specific incident, confirming a particular request was captured,
or checking exactly what a redacted body looks like after capture. Remember
that normal (non-slow, non-error) requests are
[sampled](concepts.md#sampling-and-inverse-probability-weighting), so not every
real request has a row here — slow and error requests always do.

## Refresh endpoint

`performance/api/raw-logs/` returns the page context as JSON, staff-only.
