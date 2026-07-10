from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help: str = (
        "Export SystemResourceSnapshot rows for a service and time range to CSV."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--service", required=True, help="service_name value, e.g. django-web"
        )
        parser.add_argument(
            "--start", required=True, help="ISO datetime, e.g. 2026-05-01T00:00:00"
        )
        parser.add_argument(
            "--end", required=True, help="ISO datetime, e.g. 2026-05-20T23:59:59"
        )
        parser.add_argument(
            "--output", default="-", help="Output file path (default: stdout)"
        )

    def handle(self, *args, **options):
        from django_perfy.models import SystemResourceSnapshot

        service: str = options["service"]
        try:
            start = datetime.fromisoformat(options["start"]).replace(
                tzinfo=timezone.utc
            )
            end = datetime.fromisoformat(options["end"]).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise CommandError(f"Invalid date format: {exc}") from exc

        qs = SystemResourceSnapshot.objects.filter(
            service_name=service,
            captured_at__gte=start,
            captured_at__lte=end,
        ).order_by("captured_at")

        fields: list[str] = [
            "captured_at",
            "service_type",
            "service_name",
            "instance_id",
            "cpu_percent",
            "ram_used_mb",
            "ram_total_mb",
            "ram_percent",
            "disk_used_gb",
            "disk_total_gb",
            "disk_percent",
            "open_file_descriptors",
            "active_threads",
            "celery_active_tasks",
            "celery_queued_tasks",
            "celery_reserved_tasks",
            "redis_used_memory_mb",
            "redis_connected_clients",
            "redis_blocked_clients",
            "postgres_active_connections",
            "postgres_idle_connections",
            "postgres_db_size_mb",
        ]

        output: str = options["output"]
        if output == "-":
            writer = csv.writer(sys.stdout)
        else:
            f = open(output, "w", newline="", encoding="utf-8")
            writer = csv.writer(f)

        writer.writerow(fields)
        count: int = 0
        for row in qs.iterator(chunk_size=500):
            writer.writerow([getattr(row, field, "") for field in fields])
            count += 1

        if output != "-":
            f.close()
            self.stdout.write(self.style.SUCCESS(f"Exported {count} rows to {output}"))
        else:
            sys.stderr.write(f"Exported {count} rows\n")
