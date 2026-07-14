# WebSocket monitoring

`WebSocketLoggingMixin` instruments a Django Channels `AsyncWebsocketConsumer`
and writes one `WebSocketEventLog` row per connect, disconnect, receive and
send event.

```python
from channels.generic.websocket import AsyncWebsocketConsumer
from django_perfy.mixins import WebSocketLoggingMixin

class ChatConsumer(WebSocketLoggingMixin, AsyncWebsocketConsumer):
    ...
```

## Why it wraps the low-level handlers

The mixin overrides Channels' low-level dispatch methods —
`websocket_connect`, `websocket_disconnect`, `websocket_receive` — rather than
the application-level `connect()`, `disconnect()`, `receive()` methods a
consumer normally implements. Channels always calls the low-level handlers
before dispatching to the application-level ones, so instrumentation here
fires even when a consumer subclass overrides `connect()`/`receive()` without
calling `super()`. If the mixin hooked the application-level methods instead,
a consumer that forgot `super().receive(...)` would silently stop being
monitored.

`send()` is the one application-level method it does wrap directly — consumers
call it to push data to the client, and nothing above it in the call stack
would otherwise see that traffic.

## What gets recorded

| Event | Direction | Extra fields |
| --- | --- | --- |
| `connect` | inbound | — |
| `disconnect` | inbound | `connection_duration_ms` (time since connect) |
| `receive` | inbound | `message_size_bytes` |
| `send` | outbound | `message_size_bytes` |

Every event also carries `processing_time_ms` (how long the wrapped handler
took), a `connection_id` (a UUID generated at connect and reused for every
event on that connection, so a session's full lifecycle can be reconstructed),
`consumer_name`, and the same HMAC user hash the API middleware uses.

## Non-blocking writes

Each event schedules its DB write via `asyncio.ensure_future(...)` — the
consumer's own coroutine isn't blocked waiting for the write to land, and a
slow or failed write doesn't delay the WebSocket traffic it's describing.

## Sampling

There is no separate WebSocket sampling rate — every connect, disconnect,
send and receive event is recorded when `ENABLED` is `True`. Use
`RETENTION_DAYS_RAW` to bound how long raw event rows are kept if volume gets
large; the dashboard's WebSocket page and `PerformanceSummary` rollups are
built from these rows the same way the API pages are built from
`APIRequestLog`.
