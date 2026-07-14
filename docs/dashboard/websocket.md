# WebSocket page

`performance/websocket/` — activity and timing for Django Channels consumers
instrumented with [`WebSocketLoggingMixin`](../features/websocket-monitoring.md).
Every event (connect, disconnect, receive, send) is recorded in
`WebSocketEventLog`; unlike API requests, WebSocket events are **not sampled** —
all of them are stored when `ENABLED` is on, so counts here are exact, not
weighted.

## KPI tiles

| Tile | Source | Meaning |
| --- | --- | --- |
| Active connections | `connects − disconnects` over the range (floored at 0) | Approximate live connections. A long range inflates this if sessions predate the window; read it alongside the lifecycle chart. |
| Avg processing time | `Avg(processing_time_ms)` | Mean time the wrapped handler took across all events. |
| Inbound messages | `Count(event_type = receive)` | Client → server frames. |
| Outbound messages | `Count(event_type = send)` | Server → client frames. |

## Connection lifecycle chart

Connects vs disconnects per hour (`TruncHour`). A persistent gap between the two
lines means connections are accumulating (or leaking); they should track each
other over a healthy period.

## Messages per consumer

Inbound vs outbound counts grouped by `consumer_name`. Identifies which
consumer carries the traffic and whether it is read-heavy or write-heavy.

## Connection duration histogram

Disconnect events carry `connection_duration_ms` (time since the matching
connect). Up to 5,000 recent durations are bucketed into 10 bins from 0 to the
longest observed duration, labelled in seconds. It shows whether sessions are
mostly short-lived or long-lived.

## Consumer breakdown table

One row per consumer (`consumer_name`), combining several aggregates:

| Column | Source | Meaning |
| --- | --- | --- |
| Active | `connects − disconnects` for that consumer | Approximate live connections on it. |
| Avg processing | `Avg(processing_time_ms)` | Mean handler time. |
| p95 processing | 95th percentile of that consumer's processing times | Tail latency for its events. |
| Avg message size | `Avg(message_size_bytes)` | Typical frame size. |
| Fanout | `outbound / max(inbound, 1)` | Broadcast ratio — see below. |

**Fanout** is the number of outbound (server → client) frames per inbound
frame. A value near 1 is request/response; a high value flags a
broadcast-heavy consumer (one inbound message triggering many sends), which is
where WebSocket load tends to concentrate.

## Event latency table

Processing-time percentiles grouped by **consumer + event type**
(`_ws_event_latency`), sorted by p95 descending, over up to 50,000 recent
events. This is the breakdown that exposes slow `connect` events specifically —
the real user-facing WebSocket pain (a slow handshake) that a single
consumer-wide average would hide. Each row shows count and p50/p95/p99 for that
`(consumer, event)` pair.

## Refresh endpoint

`performance/api/websocket/` returns the page context as JSON, staff-only.
