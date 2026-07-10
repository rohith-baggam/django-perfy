from __future__ import annotations

import threading

from django.apps import AppConfig


class PerformanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_perfy"
    label = "performance"
    verbose_name = "Performance Monitor"

    def ready(self) -> None:
        from django_perfy import checks  # noqa: F401 — register system checks
        from django_perfy.router import register_router

        # Route the performance app to PERFORMANCE_MONITOR["DATABASE"]. No-op
        # while that stays "default"; pins reads/writes/migrations to the
        # secondary alias otherwise.
        register_router()

        # Inject the correlation view into the Django admin — but only when the
        # admin app is installed, so projects without it still load cleanly.
        from django.apps import apps as django_apps

        if django_apps.is_installed("django.contrib.admin"):
            self._register_admin_correlation_view()

        # Start background snapshot thread for the web process.
        # This captures Django-web metrics every 15 minutes without needing
        # Celery Beat. Celery Beat still handles Celery-worker snapshots.
        _start_web_snapshot_timer()

        # Start background aggregation timer — populates PerformanceSummary
        # every 2 minutes without requiring Celery Beat to be running.
        _start_aggregation_timer()

    def _register_admin_correlation_view(self) -> None:
        from django.contrib import admin
        from django.urls import path

        from django_perfy.views import CorrelationView

        extra_urls = [
            path(
                "performance/correlation/",
                admin.site.admin_view(CorrelationView.as_view()),
                name="performance_correlation",
            ),
        ]
        admin.site.get_urls = _prepend_urls(admin.site.get_urls, extra_urls)


def _prepend_urls(original_get_urls, extra):
    def get_urls():
        return extra + original_get_urls()

    return get_urls


def _take_web_snapshot() -> None:
    """Collect and persist a SystemResourceSnapshot for this web process."""
    try:
        from django.db import close_old_connections

        from django_perfy.collectors import collect_process_metrics
        from django_perfy.models import SystemResourceSnapshot
        from django_perfy.utils import get_settings

        cfg = get_settings()
        if not cfg.get("ENABLED", True):
            return

        close_old_connections()
        data = collect_process_metrics("django-web", "web")
        SystemResourceSnapshot.objects.create(**data)
    except Exception:
        pass  # Never crash the process — snapshots are best-effort


def _start_web_snapshot_timer() -> None:
    """
    Spawn a daemon timer that fires _take_web_snapshot() every 15 minutes.
    Daemon threads are killed automatically when the process exits.
    Guard: only start in the actual server process, not during migrate/shell/tests.
    """
    import sys

    # Skip for management commands that aren't the runserver/asgi worker
    argv = sys.argv
    if len(argv) >= 2 and argv[1] in (
        "migrate",
        "makemigrations",
        "shell",
        "test",
        "check",
        "collectstatic",
        "showmigrations",
        "dbshell",
        "dumpdata",
        "loaddata",
    ):
        return

    def _run() -> None:
        _take_web_snapshot()
        interval = 15 * 60
        try:
            from django_perfy.utils import get_settings

            interval = get_settings().get("RESOURCE_SNAPSHOT_INTERVAL_MINUTES", 15) * 60
        except Exception:
            pass
        t = threading.Timer(interval, _run)
        t.daemon = True
        t.start()

    # First snapshot after 60 s so the server is fully warm before we collect
    t = threading.Timer(60, _run)
    t.daemon = True
    t.start()


_MANAGEMENT_COMMANDS_TO_SKIP = frozenset(
    (
        "migrate",
        "makemigrations",
        "shell",
        "test",
        "check",
        "collectstatic",
        "showmigrations",
        "dbshell",
        "dumpdata",
        "loaddata",
        "rebuild_summaries",
        "performance_report",
        "export_resource_snapshots",
    )
)


def _aggregate_minute_summaries() -> None:
    """Compute and upsert PerformanceSummary rows for the last 2-minute window."""
    try:
        from django.db import close_old_connections

        from django_perfy.tasks import (
            aggregate_api_logs,
            aggregate_websocket_logs,
        )
        from django_perfy.utils import get_settings

        if not get_settings().get("ENABLED", True):
            return

        close_old_connections()
        aggregate_api_logs("minute")
        aggregate_websocket_logs("minute")
    except Exception:
        pass  # Never crash the process — aggregation is best-effort


def _start_aggregation_timer() -> None:
    """
    Spawn a daemon timer that calls _aggregate_minute_summaries() every 2 minutes.
    This ensures PerformanceSummary is populated even when Celery Beat is not
    running. Beat-triggered runs are safe to overlap — update_or_create is
    idempotent on the (log_type, endpoint_or_consumer, granularity, window_start)
    unique key.
    """
    import sys

    argv = sys.argv
    if len(argv) >= 2 and argv[1] in _MANAGEMENT_COMMANDS_TO_SKIP:
        return

    def _run() -> None:
        _aggregate_minute_summaries()
        t = threading.Timer(120, _run)
        t.daemon = True
        t.start()

    # First aggregation after 2 minutes so there is data in the window
    t = threading.Timer(120, _run)
    t.daemon = True
    t.start()
