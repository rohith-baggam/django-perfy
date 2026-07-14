# Management commands

## `rebuild_summaries`

Backfills `PerformanceSummary` rows from existing raw logs for a given window
— use after changing retention, recovering from an aggregation gap, or
seeding summaries for historical data that predates the app being installed.

```bash
python manage.py rebuild_summaries --start 2026-01-01T00:00:00 --end 2026-05-20T00:00:00
```

| Flag | Required | Default | Values |
| --- | --- | --- | --- |
| `--start` | yes | — | ISO datetime |
| `--end` | yes | — | ISO datetime |
| `--log-type` | no | `both` | `api`, `websocket`, `both` |
| `--granularity` | no | `hour` | `minute`, `hour`, `both` |

Walks the window in fixed steps (one minute or one hour, depending on
granularity) and calls the same aggregation logic the Celery tasks use for
each step — safe to re-run over an already-summarized range, since
aggregation is idempotent.

## `performance_report`

Prints a plain-text summary to the terminal: p95/p99 by endpoint and by
WebSocket consumer for the last 24 hours (from hourly `PerformanceSummary`
rows), plus the latest resource snapshot per service. No flags — useful as a
quick health check from a shell or a cron job piping into a log, distinct
from the PDF report engine covered in
[Dashboard & reports](../features/dashboard-and-reports.md).

```bash
python manage.py performance_report
```

## `export_resource_snapshots`

Exports `SystemResourceSnapshot` rows for one service and time range to CSV.

```bash
python manage.py export_resource_snapshots \
  --service django-web \
  --start 2026-05-01T00:00:00 \
  --end 2026-05-20T23:59:59 \
  --output snapshots.csv
```

| Flag | Required | Default | Notes |
| --- | --- | --- | --- |
| `--service` | yes | — | Matches `service_name`, e.g. `django-web` |
| `--start` | yes | — | ISO datetime |
| `--end` | yes | — | ISO datetime |
| `--output` | no | `-` (stdout) | File path, or `-` to stream CSV to stdout |

Streams rows via `iterator(chunk_size=500)`, so exporting a large window
doesn't load the whole result set into memory at once.
