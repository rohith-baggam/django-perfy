from __future__ import annotations

import csv

from django.contrib import admin
from django.http import HttpResponse

from django_perfy.models import (
    APIRequestLog,
    PerformanceSummary,
    SystemResourceSnapshot,
    WebSocketEventLog,
)

for _model in (
    APIRequestLog,
    WebSocketEventLog,
    SystemResourceSnapshot,
    PerformanceSummary,
):
    try:
        admin.site.unregister(_model)
    except admin.sites.NotRegistered:
        pass


def _csv_export(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{modeladmin.model._meta.model_name}_export.csv"'
    )
    fields: list[str] = [
        f.name for f in modeladmin.model._meta.get_fields() if hasattr(f, "column")
    ]
    writer = csv.writer(response)
    writer.writerow(fields)
    for obj in queryset.iterator(chunk_size=500):
        writer.writerow([getattr(obj, f, "") for f in fields])
    return response


_csv_export.short_description = "Export selected rows to CSV"


@admin.register(APIRequestLog)
class APIRequestLogAdmin(admin.ModelAdmin):
    list_display: list[str] = [
        "endpoint",
        "method",
        "status_code",
        "response_time_ms",
        "db_query_count",
        "concurrent_requests",
        "created_at",
    ]
    list_filter: list[str] = ["status_code", "method"]
    search_fields: list[str] = ["endpoint"]
    date_hierarchy: str = "created_at"
    readonly_fields: list[str] = [
        f.name for f in APIRequestLog._meta.get_fields() if hasattr(f, "column")
    ]
    actions: list = [_csv_export]
    ordering: list[str] = ["-created_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(WebSocketEventLog)
class WebSocketEventLogAdmin(admin.ModelAdmin):
    list_display = [
        "consumer_name",
        "event_type",
        "direction",
        "processing_time_ms",
        "message_size_bytes",
        "created_at",
    ]
    list_filter = ["consumer_name", "event_type", "direction"]
    date_hierarchy = "created_at"
    readonly_fields = [
        f.name for f in WebSocketEventLog._meta.get_fields() if hasattr(f, "column")
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(SystemResourceSnapshot)
class SystemResourceSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "service_type",
        "service_name",
        "cpu_percent",
        "ram_percent",
        "disk_percent",
        "celery_active_tasks",
        "captured_at",
    ]
    list_filter = ["service_type", "service_name"]
    date_hierarchy = "captured_at"
    readonly_fields = [
        f.name
        for f in SystemResourceSnapshot._meta.get_fields()
        if hasattr(f, "column")
    ]
    actions = [_csv_export]
    ordering = ["-captured_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


class _DateRangeRequiredMixin:
    """Requires a date filter to be active before showing results."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        has_date_filter = any(
            k in request.GET
            for k in [
                "window_start__gte",
                "window_start__lte",
                "window_start__year",
                "window_start__month",
                "window_start__day",
                "created_at__gte",
                "created_at__lte",
            ]
        )
        if not has_date_filter:
            return qs.none()
        return qs


@admin.register(PerformanceSummary)
class PerformanceSummaryAdmin(_DateRangeRequiredMixin, admin.ModelAdmin):
    list_display = [
        "endpoint_or_consumer",
        "log_type",
        "granularity",
        "window_start",
        "total_requests",
        "p95_ms",
        "p99_ms",
        "error_count",
    ]
    list_filter = ["log_type", "granularity"]
    search_fields = ["endpoint_or_consumer"]
    date_hierarchy = "window_start"
    readonly_fields = [
        f.name for f in PerformanceSummary._meta.get_fields() if hasattr(f, "column")
    ]
    ordering = ["-window_start", "-p99_ms"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
