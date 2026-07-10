from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help: str = "Backfill PerformanceSummary from existing raw logs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-type",
            choices=["api", "websocket", "both"],
            default="both",
        )
        parser.add_argument(
            "--start", required=True, help="ISO datetime, e.g. 2026-01-01T00:00:00"
        )
        parser.add_argument(
            "--end", required=True, help="ISO datetime, e.g. 2026-05-20T00:00:00"
        )
        parser.add_argument(
            "--granularity", choices=["minute", "hour", "both"], default="hour"
        )

    def handle(self, *args, **options):
        from django_perfy.tasks import (
            aggregate_api_logs,
            aggregate_websocket_logs,
        )

        log_type: str = options["log_type"]
        granularity: str = options["granularity"]
        start = datetime.fromisoformat(options["start"]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(options["end"]).replace(tzinfo=timezone.utc)

        granularities: list[str] = (
            ["minute", "hour"] if granularity == "both" else [granularity]
        )
        log_types: list[str] = (
            ["api", "websocket"] if log_type == "both" else [log_type]
        )

        for gran in granularities:
            delta = timedelta(minutes=1) if gran == "minute" else timedelta(hours=1)
            cursor: datetime = start
            while cursor < end:
                window_iso = cursor.isoformat()
                for lt in log_types:
                    if lt == "api":
                        aggregate_api_logs(gran, window_iso)
                    else:
                        aggregate_websocket_logs(gran, window_iso)
                cursor += delta

        self.stdout.write(self.style.SUCCESS("rebuild_summaries complete."))
