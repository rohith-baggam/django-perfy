from __future__ import annotations

from datetime import datetime, timezone

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View


@method_decorator(staff_member_required, name="dispatch")
class CorrelationView(View):
    """
    Admin view: correlates API latency with system resource utilization.

    GET params:
        endpoint  — the endpoint pattern to filter (e.g. api/messages/<uuid>/)
        start     — ISO datetime string for window start
        end       — ISO datetime string for window end
    """

    template_name = "performance/correlation_view.html"

    def get(self, request):
        from django_perfy.models import APIRequestLog, SystemResourceSnapshot

        endpoint = request.GET.get("endpoint", "").strip()
        start_str = request.GET.get("start", "").strip()
        end_str = request.GET.get("end", "").strip()

        api_rows = []
        resource_rows = []
        errors = []

        if endpoint and start_str and end_str:
            try:
                window_start = datetime.fromisoformat(start_str).replace(
                    tzinfo=timezone.utc
                )
                window_end = datetime.fromisoformat(end_str).replace(
                    tzinfo=timezone.utc
                )
            except ValueError as exc:
                errors.append(f"Invalid date format: {exc}")
                window_start = window_end = None

            if window_start and window_end:
                api_qs = (
                    APIRequestLog.objects.filter(
                        endpoint=endpoint,
                        created_at__gte=window_start,
                        created_at__lte=window_end,
                    )
                    .order_by("created_at")
                    .values(
                        "created_at",
                        "response_time_ms",
                        "status_code",
                        "db_query_count",
                        "concurrent_requests",
                    )
                )
                api_rows = list(api_qs[:500])

                resource_qs = (
                    SystemResourceSnapshot.objects.filter(
                        captured_at__gte=window_start,
                        captured_at__lte=window_end,
                    )
                    .order_by("captured_at", "service_name")
                    .values(
                        "captured_at",
                        "service_type",
                        "service_name",
                        "cpu_percent",
                        "ram_percent",
                        "disk_percent",
                        "celery_active_tasks",
                        "postgres_active_connections",
                        "redis_connected_clients",
                    )
                )
                resource_rows = list(resource_qs[:500])

        context = {
            "endpoint": endpoint,
            "start": start_str,
            "end": end_str,
            "api_rows": api_rows,
            "resource_rows": resource_rows,
            "errors": errors,
            "title": "Performance Correlation View",
        }
        return render(request, self.template_name, context)
