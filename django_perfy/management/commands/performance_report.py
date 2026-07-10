from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help: str = (
        "Print a terminal summary of the last 24h API/WebSocket latency and latest resource snapshots."
    )

    def handle(self, *args, **options):
        from django_perfy.models import (
            PerformanceSummary,
            SystemResourceSnapshot,
        )

        since = timezone.now() - timedelta(hours=24)

        self.stdout.write("\n=== API p95 / p99 (last 24h, by endpoint) ===\n")
        api_summaries = (
            PerformanceSummary.objects.filter(
                log_type="api",
                granularity="hour",
                window_start__gte=since,
            )
            .order_by("endpoint_or_consumer", "-window_start")
            .values(
                "endpoint_or_consumer",
                "p95_ms",
                "p99_ms",
                "total_requests",
                "error_count",
            )
        )

        seen = set()
        for row in api_summaries:
            ep: str = row["endpoint_or_consumer"]
            if ep in seen:
                continue
            seen.add(ep)
            self.stdout.write(
                f"  {ep:<60} p95={row['p95_ms']:>6}ms  p99={row['p99_ms']:>6}ms  "
                f"reqs={row['total_requests']:>6}  errors={row['error_count']}"
            )

        if not seen:
            self.stdout.write("  (no hourly summaries in the last 24h)")

        self.stdout.write("\n=== WebSocket p95 / p99 (last 24h, by consumer) ===\n")
        ws_summaries = (
            PerformanceSummary.objects.filter(
                log_type="websocket",
                granularity="hour",
                window_start__gte=since,
            )
            .order_by("endpoint_or_consumer", "-window_start")
            .values("endpoint_or_consumer", "p95_ms", "p99_ms", "total_requests")
        )

        seen_ws = set()
        for row in ws_summaries:
            ep: str = row["endpoint_or_consumer"]
            if ep in seen_ws:
                continue
            seen_ws.add(ep)
            self.stdout.write(
                f"  {ep:<60} p95={row['p95_ms']:>6}ms  p99={row['p99_ms']:>6}ms  "
                f"reqs={row['total_requests']:>6}"
            )

        if not seen_ws:
            self.stdout.write("  (no hourly summaries in the last 24h)")

        self.stdout.write("\n=== Latest System Resource Snapshot per Service ===\n")
        services = SystemResourceSnapshot.objects.order_by(
            "service_name", "-captured_at"
        ).values(
            "service_name",
            "service_type",
            "cpu_percent",
            "ram_percent",
            "disk_percent",
            "celery_active_tasks",
            "captured_at",
        )

        seen_svc = set()
        for row in services:
            svc: str = row["service_name"]
            if svc in seen_svc:
                continue
            seen_svc.add(svc)
            self.stdout.write(
                f"  {svc:<40} [{row['service_type']}]  "
                f"cpu={row['cpu_percent']}%  ram={row['ram_percent']}%  "
                f"disk={row['disk_percent'] or '-'}%  "
                f"celery_active={row['celery_active_tasks'] if row['celery_active_tasks'] is not None else '-'}  "
                f"@ {row['captured_at']}"
            )

        if not seen_svc:
            self.stdout.write("  (no snapshots recorded yet)")

        self.stdout.write("")
