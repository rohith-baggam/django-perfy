# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-10

### Added

- Initial standalone release, extracted from an internal Django service.
- API request, WebSocket event, system-resource and rolling-summary models.
- Middleware and consumer mixin for capturing API and WebSocket telemetry.
- Celery tasks for persistence, aggregation, resource snapshots and retention.
- Admin correlation view plus a Jinja2 dashboard and PDF report engine.
- `PERFORMANCE_MONITOR["DATABASE"]` option to store all telemetry in a
  secondary database, backed by the bundled `PerformanceRouter`.
- Settings-driven SMTP report emailing (`django_perfy.email.send_email`) that
  raises instead of failing silently when misconfigured.
