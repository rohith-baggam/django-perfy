# API monitoring

`PerformanceMiddleware` records one row per captured request in
`APIRequestLog`: endpoint, method, status code, response time, request/response
size, database query count and time, and concurrency at the moment the request
was handled.

## What gets measured

- **Endpoint** is the resolved URL pattern (`request.resolver_match.route`),
  not the raw path — `/api/orders/42/` and `/api/orders/17/` both roll up
  under `/api/orders/<id>/`, which is what makes the dashboard's per-endpoint
  aggregates meaningful.
- **Database query count and time** come from wrapping the connection with
  Django's `execute_wrapper` for the duration of the request — every query
  the view triggers is counted, including ones inside your own code, not
  just the ORM calls django-perfy is aware of.
- **Concurrency** is a thread-local counter incremented on request start and
  decremented on completion, giving a same-process approximation of how many
  requests were in flight at once — not a global figure across all workers.
- **User hash**, not user id. Authenticated users are identified by an
  HMAC-SHA256 hash (`USER_ID_SALT`), so raw user ids never land in the
  telemetry tables.

## Sampling

Every captured row respects `SAMPLING_RATE`, with two overrides that always
win:

- Requests at or above `SLOW_REQUEST_THRESHOLD_MS` are always recorded.
- Requests with a 4xx/5xx status are always recorded.

Everything else is recorded with probability `SAMPLING_RATE`. The dashboard
corrects for this at query time — it doesn't just count stored rows, it
weights each one by the inverse of its sampling probability, so a 10% sample
rate doesn't make throughput numbers look 10x too low.

## Non-blocking writes

The middleware submits each captured row to a small internal thread pool
(4 workers) rather than writing inline — a slow database write on the
telemetry side never adds latency to the request it's describing. If the
write fails, it's logged and dropped; a telemetry outage never turns into a
500 for real traffic.

## Header and body capture

Off by default (`CAPTURE_HEADERS`, `CAPTURE_BODY`) — see
[Configuration](../configuration.md#header-and-body-capture) for why, and how
redaction works when you turn them on.

## Excluding paths

`EXCLUDED_PATHS` is checked as a prefix match against the request path before
any timing starts — health checks and metrics endpoints skip the middleware
entirely rather than being sampled at a low rate.
