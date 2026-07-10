from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from celery import shared_task
from django.utils import timezone as dj_timezone

from django_perfy.utils import get_settings

logger = logging.getLogger(__name__)


def _queue_name() -> str:
    return get_settings()["QUEUE_NAME"]


def _performance_enabled() -> bool:
    return bool(get_settings().get("ENABLED", True))


@shared_task(
    name="django_perfy.tasks.persist_api_log",
    ignore_result=True,
    max_retries=1,
    default_retry_delay=5,
)
def persist_api_log(payload: dict) -> None:
    if not _performance_enabled():
        return
    from django_perfy.models import APIRequestLog

    try:
        APIRequestLog.objects.create(**payload)
    except Exception as exc:
        logger.warning("persist_api_log failed: %s", exc)
        raise


@shared_task(
    name="django_perfy.tasks.persist_websocket_log",
    ignore_result=True,
    max_retries=1,
    default_retry_delay=5,
)
def persist_websocket_log(payload: dict) -> None:
    if not _performance_enabled():
        return
    from django_perfy.models import WebSocketEventLog

    try:
        WebSocketEventLog.objects.create(**payload)
    except Exception as exc:
        logger.warning("persist_websocket_log failed: %s", exc)
        raise


@shared_task(
    name="django_perfy.tasks.snapshot_process_resources",
    ignore_result=True,
)
def snapshot_process_resources(service_name: str, service_type: str) -> None:
    if not _performance_enabled():
        return
    from django_perfy.collectors import collect_process_metrics
    from django_perfy.models import SystemResourceSnapshot

    try:
        data = collect_process_metrics(service_name, service_type)
        SystemResourceSnapshot.objects.create(**data)
    except Exception as exc:
        logger.warning(
            "snapshot_process_resources(%s, %s) failed: %s",
            service_name,
            service_type,
            exc,
        )


@shared_task(
    name="django_perfy.tasks.snapshot_redis_resources",
    ignore_result=True,
)
def snapshot_redis_resources() -> None:
    if not _performance_enabled():
        return
    from django_perfy.collectors import collect_redis_metrics
    from django_perfy.models import SystemResourceSnapshot

    try:
        data = collect_redis_metrics()
        SystemResourceSnapshot.objects.create(**data)
    except Exception as exc:
        logger.warning("snapshot_redis_resources failed: %s", exc)


@shared_task(
    name="django_perfy.tasks.snapshot_postgres_resources",
    ignore_result=True,
)
def snapshot_postgres_resources() -> None:
    if not _performance_enabled():
        return
    from django_perfy.collectors import collect_postgres_metrics
    from django_perfy.models import SystemResourceSnapshot

    try:
        data = collect_postgres_metrics()
        SystemResourceSnapshot.objects.create(**data)
    except Exception as exc:
        logger.warning("snapshot_postgres_resources failed: %s", exc)


def _percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    idx = int(len(sorted_values) * pct / 100)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]


def _compute_and_upsert_summary(
    log_type: str,
    granularity: str,
    window_start: datetime,
    window_end: datetime,
) -> None:
    from django_perfy.models import (
        APIRequestLog,
        PerformanceSummary,
        WebSocketEventLog,
    )

    if log_type == "api":
        qs = APIRequestLog.objects.filter(
            created_at__gte=window_start, created_at__lt=window_end
        )
        group_field: str = "endpoint"
    else:
        qs = WebSocketEventLog.objects.filter(
            created_at__gte=window_start, created_at__lt=window_end
        )
        group_field: str = "consumer_name"

    groups: dict[str, list] = {}
    for row in qs.iterator(chunk_size=500):
        key = getattr(row, group_field)
        groups.setdefault(key, []).append(row)

    for endpoint_or_consumer, rows in groups.items():
        if log_type == "api":
            times = sorted(r.response_time_ms for r in rows)
            error_count: int = sum(1 for r in rows if r.status_code >= 400)
            sizes: list[int] = [
                r.request_size_bytes for r in rows if r.request_size_bytes
            ]
            avg_req_size: int | None = (sum(sizes) // len(sizes)) if sizes else None
        else:
            times = sorted(
                r.processing_time_ms for r in rows if r.processing_time_ms is not None
            )
            error_count: int = 0
            avg_req_size: int | None = None

        total = len(rows)
        avg_ms = (sum(times) // len(times)) if times else 0
        p50 = _percentile(times, 50)
        p95 = _percentile(times, 95)
        p99 = _percentile(times, 99)

        PerformanceSummary.objects.update_or_create(
            log_type=log_type,
            endpoint_or_consumer=endpoint_or_consumer,
            granularity=granularity,
            window_start=window_start,
            defaults={
                "total_requests": total,
                "avg_response_time_ms": avg_ms,
                "p50_ms": p50,
                "p95_ms": p95,
                "p99_ms": p99,
                "error_count": error_count,
                "avg_request_size_bytes": avg_req_size,
            },
        )


@shared_task(
    name="django_perfy.tasks.aggregate_api_logs",
    ignore_result=True,
)
def aggregate_api_logs(granularity: str, window_start_iso: str | None = None) -> None:
    if not _performance_enabled():
        return
    now = dj_timezone.now()
    if granularity == "minute":
        window_end = now.replace(second=0, microsecond=0)
        window_start = window_end - timedelta(minutes=2)
    else:
        window_end = now.replace(minute=0, second=0, microsecond=0)
        window_start = window_end - timedelta(hours=1)

    if window_start_iso:
        window_start = datetime.fromisoformat(window_start_iso)
        if granularity == "minute":
            window_end = window_start + timedelta(minutes=1)
        else:
            window_end = window_start + timedelta(hours=1)

    try:
        _compute_and_upsert_summary("api", granularity, window_start, window_end)
    except Exception as exc:
        logger.error(
            "aggregate_api_logs(%s) failed: %s", granularity, exc, exc_info=True
        )


@shared_task(
    name="django_perfy.tasks.aggregate_websocket_logs",
    ignore_result=True,
)
def aggregate_websocket_logs(
    granularity: str, window_start_iso: str | None = None
) -> None:
    if not _performance_enabled():
        return
    now = dj_timezone.now()
    if granularity == "minute":
        window_end = now.replace(second=0, microsecond=0)
        window_start = window_end - timedelta(minutes=2)
    else:
        window_end = now.replace(minute=0, second=0, microsecond=0)
        window_start = window_end - timedelta(hours=1)

    if window_start_iso:
        window_start = datetime.fromisoformat(window_start_iso)
        if granularity == "minute":
            window_end = window_start + timedelta(minutes=1)
        else:
            window_end = window_start + timedelta(hours=1)

    try:
        _compute_and_upsert_summary("websocket", granularity, window_start, window_end)
    except Exception as exc:
        logger.error(
            "aggregate_websocket_logs(%s) failed: %s", granularity, exc, exc_info=True
        )


@shared_task(
    name="django_perfy.tasks.purge_old_logs",
    ignore_result=True,
)
def purge_old_logs() -> None:
    if not _performance_enabled():
        return
    from django_perfy.models import (
        APIRequestLog,
        SystemResourceSnapshot,
        WebSocketEventLog,
    )

    cfg = get_settings()
    raw_cutoff = dj_timezone.now() - timedelta(days=cfg["RETENTION_DAYS_RAW"])
    resource_cutoff = dj_timezone.now() - timedelta(
        days=cfg["RETENTION_DAYS_RESOURCES"]
    )

    for model, cutoff, label in [
        (APIRequestLog, raw_cutoff, "APIRequestLog"),
        (WebSocketEventLog, raw_cutoff, "WebSocketEventLog"),
        (SystemResourceSnapshot, resource_cutoff, "SystemResourceSnapshot"),
    ]:
        total_deleted: int = 0
        while True:
            ids = list(
                model.objects.filter(created_at__lt=cutoff).values_list(
                    "id", flat=True
                )[:1000]
            )
            if not ids:
                break
            deleted, _ = model.objects.filter(id__in=ids).delete()
            total_deleted += deleted

        if total_deleted:
            logger.info("purge_old_logs: deleted %d rows from %s", total_deleted, label)


@shared_task(
    bind=True,
    name="django_perfy.tasks.send_report_email",
    ignore_result=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_report_email(self, report_type: str, range_key: str, email: str) -> None:
    """Render a performance report to PDF and email it as an attachment.

    Runs off the request path so the HTTP endpoint can return 202 immediately.
    SMTP/render failures are retried with backoff.
    """
    from django_perfy.reports.config import get_report_config
    from django_perfy.reports.ranges import range_label, resolve_range
    from django_perfy.reports.registry import get_spec
    from django_perfy.reports.renderer import render_report_pdf
    from django_perfy.email import send_email

    try:
        spec = get_spec(report_type)
        start, end = resolve_range(range_key)
        pdf_bytes = render_report_pdf(report_type, start, end, range_key=range_key)
        document_id = spec.builder(start, end, range_key=range_key).document_id
        cfg = get_report_config()

        subject: str = f"{spec.title} — {document_id}"
        body = (
            f"<p>Attached is the <b>{spec.title}</b> ({spec.code}) performance report "
            f"for <b>{range_label(range_key)}</b>.</p>"
            f"<p style='color:#64748b;font-size:12px'>{cfg['CLASSIFICATION']} · "
            f"Observed production telemetry (sampled &amp; inverse-probability weighted), "
            f"not a synthetic load test.</p>"
        )
        # Uses the SMTP credentials configured under PERFORMANCE_MONITOR
        # (falling back to the project's EMAIL_* settings).
        ok, message = send_email(
            receiver_email=email,
            subject=subject,
            body=body,
            attachments=[
                {
                    "filename": f"{document_id}.pdf",
                    "content_type": "application/pdf",
                    "data": pdf_bytes,
                }
            ],
        )
        if not ok:
            raise RuntimeError(f"SMTP send failed: {message}")
        logger.info("send_report_email: sent %s to %s", document_id, email)
    except Exception as exc:
        logger.warning("send_report_email failed (will retry): %s", exc)
        raise self.retry(exc=exc)


@shared_task(
    name="django_perfy.tasks.performance_pipeline_health_check",
    ignore_result=True,
)
def performance_pipeline_health_check() -> None:
    if not _performance_enabled():
        return
    from django.core.cache import cache

    from django_perfy.models import (
        APIRequestLog,
        SystemResourceSnapshot,
        WebSocketEventLog,
    )

    try:
        payload: dict[str, Any] = {
            "api_count": APIRequestLog.objects.count(),
            "ws_count": WebSocketEventLog.objects.count(),
            "snapshot_count": SystemResourceSnapshot.objects.count(),
            "timestamp": dj_timezone.now().isoformat(),
        }
        cache.set("perf_pipeline_health", payload, timeout=600)
    except Exception as exc:
        logger.warning("performance_pipeline_health_check failed: %s", exc)
