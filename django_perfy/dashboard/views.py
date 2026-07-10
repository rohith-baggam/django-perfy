from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import (
    Avg,
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Max,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import (
    ExtractHour,
    ExtractWeekDay,
    TruncHour,
    TruncMinute,
)
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_safe

from django_perfy.models import (
    APIRequestLog,
    PerformanceSummary,
    SystemResourceSnapshot,
    WebSocketEventLog,
)
from django_perfy.utils import get_settings

RANGE_MAP = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
_VALID_SERVICES = frozenset({"web", "celery_worker", "redis", "postgres"})
_TOP_ENDPOINTS_PAGE_SIZE = 10
_DB_COST_PAGE_SIZE = 20

# Dashboard SLA target (ms). Requests faster than this are "within SLA".
SLA_THRESHOLD_MS = 300
# Ranges at/under this use minute buckets for trends; larger ones use hours.
_MINUTE_BUCKET_MAX = timedelta(hours=6)


def _sampling() -> tuple[float, int]:
    """(sampling_rate, slow_threshold_ms) from the middleware config."""
    cfg = get_settings()
    rate = float(cfg.get("SAMPLING_RATE", 0.1)) or 0.1
    slow_ms = int(cfg.get("SLOW_REQUEST_THRESHOLD_MS", 500))
    return rate, slow_ms


def _weight():
    """Inverse-probability weight reconstructing each stored row's real share.

    Slow (>= threshold) and error (>= 400) requests are force-stored (weight 1).
    Everything else is random-sampled at ``rate`` and therefore represents
    ``1/rate`` real requests. Returns a fresh expression each call so it can be
    reused across multiple aggregates in one query.
    """
    rate, slow_ms = _sampling()
    inv = 1.0 / rate
    return Case(
        When(
            Q(response_time_ms__gte=slow_ms) | Q(status_code__gte=400),
            then=Value(1.0),
        ),
        default=Value(inv),
        output_field=FloatField(),
    )


def _wmul(field: str):
    """weight * <field>, as a float expression (for weighted averages)."""
    return ExpressionWrapper(_weight() * F(field), output_field=FloatField())


def _bucket_granularity(since: datetime) -> str:
    span = timezone.now() - since
    return "minute" if span <= _MINUTE_BUCKET_MAX else "hour"


def _request_weighted_percentiles(ps_qs) -> dict[str, int]:
    """Request-weighted p50/p95/p99 across PerformanceSummary rows.

    Replaces the statistically invalid ``Avg(p99)`` across endpoints: a busy or
    slow endpoint now contributes in proportion to its request volume instead of
    being diluted by many quiet endpoints.
    """
    total = 0
    acc = {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    for row in ps_qs.values("p50_ms", "p95_ms", "p99_ms", "total_requests"):
        weight = row["total_requests"] or 0
        if not weight:
            continue
        total += weight
        acc["p50"] += (row["p50_ms"] or 0) * weight
        acc["p95"] += (row["p95_ms"] or 0) * weight
        acc["p99"] += (row["p99_ms"] or 0) * weight
    if not total:
        return {"p50": 0, "p95": 0, "p99": 0}
    return {key: round(value / total) for key, value in acc.items()}


NAV_PAGE_NAMES = {
    "overview": "dashboard:overview",
    "api_performance": "dashboard:api_performance",
    "websocket": "dashboard:websocket",
    "system_resources": "dashboard:system_resources",
    "database_queries": "dashboard:database_queries",
    "correlation": "dashboard:correlation",
    "raw_logs": "dashboard:raw_logs",
}


def get_since(request) -> datetime:
    range_key = request.GET.get("range", "24h")
    return timezone.now() - RANGE_MAP.get(range_key, RANGE_MAP["24h"])


def _active_range(request) -> str:
    return request.GET.get("range", "24h")


def _build_page_url(request, page_param: str, page_num: int) -> str:
    params = request.GET.copy()
    params[page_param] = str(page_num)
    return "?" + params.urlencode()


def _parse_iso_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _serialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, tuple):
        return [_serialize(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _json_payload(data: dict[str, Any]) -> str:
    raw = json.dumps(_serialize(data), ensure_ascii=False)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[idx]


def build_kpis(since: datetime) -> dict[str, Any]:
    ps = PerformanceSummary.objects.filter(log_type="api", window_start__gte=since)
    al = APIRequestLog.objects.filter(created_at__gte=since)
    sr_web = SystemResourceSnapshot.objects.filter(
        service_type="web", captured_at__gte=since
    )

    # Sampling-corrected (inverse-probability weighted) aggregates. These
    # de-bias the fact that slow/error rows are 100%-stored while normal rows
    # are only ~10%-stored, so rates/averages off the raw table skew high.
    al_agg = al.aggregate(
        raw_total=Count("id"),
        errors=Count("id", filter=Q(status_code__gte=400)),
        peak_conc=Max("concurrent_requests"),
        w_total=Sum(_weight()),
        w_errors=Sum(_weight(), filter=Q(status_code__gte=400)),
        w_under_sla=Sum(_weight(), filter=Q(response_time_ms__lt=SLA_THRESHOLD_MS)),
        w_rt=Sum(_wmul("response_time_ms")),
        w_dbt=Sum(_wmul("db_time_ms")),
        w_dbq=Sum(_wmul("db_query_count")),
    )
    sr_agg = sr_web.aggregate(
        peak_cpu=Max("cpu_percent"),
        peak_ram=Max("ram_percent"),
    )

    pct = _request_weighted_percentiles(ps)

    w_total = float(al_agg["w_total"] or 0.0)
    denom = w_total or 1.0
    avg_rt = round((al_agg["w_rt"] or 0) / denom)
    avg_dbt = round((al_agg["w_dbt"] or 0) / denom)
    avg_dbq = round((al_agg["w_dbq"] or 0) / denom, 1)
    db_pct = round(avg_dbt / max(avg_rt, 1) * 100)
    err_rate = round((al_agg["w_errors"] or 0) / denom * 100, 1)
    sla_pct = round((al_agg["w_under_sla"] or 0) / denom * 100, 1)

    window_seconds = max((timezone.now() - since).total_seconds(), 1.0)

    return {
        # Sampling-corrected estimate of true volume (not the stored row count).
        "kpi_total_requests": round(w_total),
        "kpi_throughput_rpm": round(w_total / window_seconds * 60, 1),
        "kpi_sla_pct": sla_pct,
        "kpi_p99_ms": pct["p99"],
        "kpi_p95_ms": pct["p95"],
        "kpi_p50_ms": pct["p50"],
        "kpi_error_rate": err_rate,
        "kpi_error_count": al_agg["errors"] or 0,
        "kpi_avg_dbq": avg_dbq,
        "kpi_avg_rt": avg_rt,
        "kpi_avg_dbt": avg_dbt,
        "kpi_db_pct": db_pct,
        "kpi_peak_conc": al_agg["peak_conc"] or 0,
        "kpi_peak_cpu": float(sr_agg["peak_cpu"] or 0),
        "kpi_peak_ram": float(sr_agg["peak_ram"] or 0),
    }


def _scale_recommendations(kpis: dict[str, Any]) -> dict[str, str]:
    api_color = (
        "red"
        if (kpis["kpi_p99_ms"] > 500 or kpis["kpi_peak_conc"] > 50)
        else (
            "amber"
            if (kpis["kpi_p99_ms"] > 250 or kpis["kpi_peak_conc"] > 30)
            else "green"
        )
    )
    srv_color = (
        "red"
        if (kpis["kpi_peak_cpu"] > 80 or kpis["kpi_peak_ram"] > 85)
        else (
            "amber"
            if (kpis["kpi_peak_cpu"] > 60 or kpis["kpi_peak_ram"] > 70)
            else "green"
        )
    )
    db_color = (
        "red"
        if (kpis["kpi_avg_dbq"] > 10 or kpis["kpi_db_pct"] > 50)
        else ("amber" if kpis["kpi_avg_dbq"] > 6 else "green")
    )
    return {
        "scale_api_color": api_color,
        "scale_srv_color": srv_color,
        "scale_db_color": db_color,
        "scale_api_rec": (
            "Scale Now"
            if kpis["kpi_p99_ms"] > 500
            else ("Monitor" if kpis["kpi_p99_ms"] > 250 else "Healthy")
        ),
        "scale_srv_rec": (
            "Scale Server"
            if kpis["kpi_peak_cpu"] > 80
            else ("Monitor" if kpis["kpi_peak_cpu"] > 60 else "Healthy")
        ),
        "scale_db_rec": (
            "Optimize Queries"
            if kpis["kpi_avg_dbq"] > 10
            else ("Monitor" if kpis["kpi_avg_dbq"] > 6 else "Healthy")
        ),
    }


def _latency_series(since: datetime) -> list[dict[str, Any]]:
    """Request-weighted p50/p95/p99 per summary window.

    Each window's percentile is weighted by per-endpoint request volume rather
    than a flat ``Avg`` across endpoints, so a single hot endpoint is no longer
    averaged away into a calm-looking line.
    """
    acc: dict[Any, dict[str, float]] = defaultdict(
        lambda: {"req": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
    )
    rows = (
        PerformanceSummary.objects.filter(log_type="api", window_start__gte=since)
        .values("window_start", "p50_ms", "p95_ms", "p99_ms", "total_requests")
        .order_by("window_start")
    )
    for row in rows:
        weight = row["total_requests"] or 0
        if not weight:
            continue
        slot = acc[row["window_start"]]
        slot["req"] += weight
        slot["p50"] += (row["p50_ms"] or 0) * weight
        slot["p95"] += (row["p95_ms"] or 0) * weight
        slot["p99"] += (row["p99_ms"] or 0) * weight
    series = []
    for window_start in sorted(acc):
        slot = acc[window_start]
        req = slot["req"] or 1
        series.append(
            {
                "window_start": window_start,
                "p50": slot["p50"] / req,
                "p95": slot["p95"] / req,
                "p99": slot["p99"] / req,
            }
        )
    return series


def _traffic_series(since: datetime) -> list[dict[str, Any]]:
    """Sampling-corrected throughput, error-rate and SLA% per time bucket."""
    granularity = _bucket_granularity(since)
    trunc = TruncMinute if granularity == "minute" else TruncHour
    rows = (
        APIRequestLog.objects.filter(created_at__gte=since)
        .annotate(bucket=trunc("created_at"))
        .values("bucket")
        .annotate(
            w_total=Sum(_weight()),
            w_err=Sum(_weight(), filter=Q(status_code__gte=400)),
            w_sla=Sum(_weight(), filter=Q(response_time_ms__lt=SLA_THRESHOLD_MS)),
        )
        .order_by("bucket")
    )
    out = []
    for row in rows:
        total = float(row["w_total"] or 0.0) or 1.0
        out.append(
            {
                "ts": row["bucket"].isoformat(),
                "count": round(float(row["w_total"] or 0.0)),
                "err_rate": round((row["w_err"] or 0) / total * 100, 2),
                "sla": round((row["w_sla"] or 0) / total * 100, 1),
            }
        )
    return out


def _db_offenders(since: datetime, limit: int = 10) -> list[dict[str, Any]]:
    """Endpoints ranked by estimated TOTAL DB time contribution.

    avg DB-time-per-request alone hides cheap-but-constant offenders; ranking by
    ``weighted_volume * avg_db_ms`` surfaces where fixing queries pays off most.
    """
    rows = list(
        APIRequestLog.objects.filter(created_at__gte=since)
        .values("endpoint")
        .annotate(
            w=Sum(_weight()),
            w_dbt=Sum(_wmul("db_time_ms")),
            w_dbq=Sum(_wmul("db_query_count")),
        )
    )
    for row in rows:
        weight = float(row["w"] or 0.0) or 1.0
        row["est_total_db_ms"] = round(float(row["w_dbt"] or 0.0))
        row["avg_db_queries"] = round(float(row["w_dbq"] or 0.0) / weight, 1)
    rows.sort(key=lambda r: r["est_total_db_ms"], reverse=True)
    grand_total = sum(r["est_total_db_ms"] for r in rows) or 1
    top = rows[:limit]
    for row in top:
        row["share_pct"] = round(row["est_total_db_ms"] / grand_total * 100, 1)
    return top


def _ws_event_latency(since: datetime) -> list[dict[str, Any]]:
    """Per consumer + event-type processing-time percentiles.

    This is the breakdown that exposes slow ``connect`` events (the real
    user-facing WebSocket pain) that aggregate consumer averages hide.
    """
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for consumer, event, ms in (
        WebSocketEventLog.objects.filter(
            created_at__gte=since, processing_time_ms__isnull=False
        )
        .order_by("-created_at")
        .values_list("consumer_name", "event_type", "processing_time_ms")[:50000]
    ):
        grouped[(consumer, event)].append(ms)
    out = []
    for (consumer, event), values in grouped.items():
        values.sort()
        out.append(
            {
                "consumer": consumer,
                "event": event,
                "count": len(values),
                "p50": _pct_from_sorted(values, 50),
                "p95": _pct_from_sorted(values, 95),
                "p99": _pct_from_sorted(values, 99),
            }
        )
    out.sort(key=lambda r: r["p95"] or 0, reverse=True)
    return out


def _pct_from_sorted(sorted_values: list[int], pct: float) -> int | None:
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * pct / 100))
    return sorted_values[idx]


def _error_by_status(since: datetime) -> list[dict[str, Any]]:
    return list(
        APIRequestLog.objects.filter(status_code__gte=400, created_at__gte=since)
        .values("status_code")
        .annotate(count=Count("id"))
        .order_by("status_code")
    )


def _top_endpoints(
    request, since: datetime
) -> tuple[list[dict[str, Any]], str, int, int]:
    order_map = {
        "slowest": "-avg_p99",
        "errored": "-total_errors",
        "busy": "-total_requests",
    }
    active_tab = request.GET.get("tab", "slowest")
    order_field = order_map.get(active_tab, "-avg_p99")

    try:
        page = max(int(request.GET.get("ep_page", "1") or 1), 1)
    except (ValueError, TypeError):
        page = 1

    base_qs = (
        PerformanceSummary.objects.filter(log_type="api", window_start__gte=since)
        .values("endpoint_or_consumer")
        .annotate(
            total_requests=Sum("total_requests"),
            avg_p99=Avg("p99_ms"),
            total_errors=Sum("error_count"),
        )
        .order_by(order_field)
    )
    total_count = base_qs.count()
    total_pages = max(
        1, (total_count + _TOP_ENDPOINTS_PAGE_SIZE - 1) // _TOP_ENDPOINTS_PAGE_SIZE
    )
    page = min(page, total_pages)
    offset = (page - 1) * _TOP_ENDPOINTS_PAGE_SIZE
    summary_rows = list(base_qs[offset : offset + _TOP_ENDPOINTS_PAGE_SIZE])

    dbq_rows = {
        row["endpoint"]: row["avg_db"]
        for row in APIRequestLog.objects.filter(created_at__gte=since)
        .values("endpoint")
        .annotate(avg_db=Avg("db_query_count"))
    }

    for row in summary_rows:
        row["avg_db_queries"] = round(
            float(dbq_rows.get(row["endpoint_or_consumer"], 0) or 0), 1
        )

    return summary_rows, active_tab, page, total_pages


def _api_drilldown_rows(
    request, since: datetime, limit: int = 16
) -> tuple[list[dict[str, Any]], int, int]:
    qs = APIRequestLog.objects.filter(created_at__gte=since).order_by("-created_at")
    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(endpoint__icontains=search)

    method = request.GET.get("method", "all")
    if method != "all":
        qs = qs.filter(method=method.upper())

    status = request.GET.get("status", "all")
    if status == "2xx":
        qs = qs.filter(status_code__lt=400)
    elif status == "4xx":
        qs = qs.filter(status_code__gte=400, status_code__lt=500)
    elif status == "5xx":
        qs = qs.filter(status_code__gte=500)

    if request.GET.get("slow", "all") == "slow":
        qs = qs.filter(response_time_ms__gte=500)

    try:
        page = max(int(request.GET.get("page", "1") or 1), 1)
    except (ValueError, TypeError):
        page = 1

    total_count = qs.count()
    total_pages = max(1, (total_count + limit - 1) // limit)
    page = min(page, total_pages)
    offset = (page - 1) * limit

    rows = list(
        qs.values(
            "created_at",
            "method",
            "endpoint",
            "status_code",
            "response_time_ms",
            "db_query_count",
            "db_time_ms",
            "concurrent_requests",
        )[offset : offset + limit]
    )
    return rows, page, total_pages


def _overview_context(request) -> dict[str, Any]:
    since = get_since(request)
    kpis = build_kpis(since)
    scale = _scale_recommendations(kpis)
    latency_series = _latency_series(since)
    traffic_series = _traffic_series(since)
    error_counts = _error_by_status(since)
    top_endpoints, active_tab, ep_page, ep_total_pages = _top_endpoints(request, since)

    page_data = {
        "kpis": kpis,
        "scale": scale,
        "latency_series": [
            {
                "ts": row["window_start"].isoformat(),
                "p50": round(row["p50"] or 0),
                "p95": round(row["p95"] or 0),
                "p99": round(row["p99"] or 0),
            }
            for row in latency_series
        ],
        "traffic_series": traffic_series,
        "error_by_status": [
            {"code": row["status_code"], "count": row["count"]} for row in error_counts
        ],
        "top_endpoints": top_endpoints,
        "active_tab": active_tab,
    }

    return {
        **kpis,
        **scale,
        "top_endpoints": top_endpoints,
        "active_tab": active_tab,
        "ep_page": ep_page,
        "ep_total_pages": ep_total_pages,
        "ep_prev_url": (
            _build_page_url(request, "ep_page", ep_page - 1) if ep_page > 1 else None
        ),
        "ep_next_url": (
            _build_page_url(request, "ep_page", ep_page + 1)
            if ep_page < ep_total_pages
            else None
        ),
        "active_page": NAV_PAGE_NAMES["overview"],
        "active_range": _active_range(request),
        "latency_series_json": json.dumps(page_data["latency_series"]),
        "error_by_status_json": json.dumps(page_data["error_by_status"]),
        "page_data_json": _json_payload(page_data),
    }


def _api_performance_context(request) -> dict[str, Any]:
    since = get_since(request)
    kpis = build_kpis(since)
    latency_series = _latency_series(since)
    scatter_rows = list(
        APIRequestLog.objects.filter(created_at__gte=since)
        .order_by("-created_at")
        .values("response_time_ms", "db_query_count", "status_code")[:500]
    )
    conc_series = list(
        APIRequestLog.objects.filter(created_at__gte=since)
        .order_by("created_at")
        .values("created_at", "concurrent_requests")[:500]
    )
    drilldown_rows, drilldown_page, drilldown_total_pages = _api_drilldown_rows(
        request, since, limit=16
    )
    traffic_series = _traffic_series(since)

    page_data = {
        "kpis": kpis,
        "latency_series": [
            {
                "ts": row["window_start"].isoformat(),
                "p50": round(row["p50"] or 0),
                "p95": round(row["p95"] or 0),
                "p99": round(row["p99"] or 0),
            }
            for row in latency_series
        ],
        "traffic_series": traffic_series,
        "scatter": [
            {
                "x": row["response_time_ms"],
                "y": row["db_query_count"],
                "sc": row["status_code"],
            }
            for row in scatter_rows
        ],
        "conc_series": [
            {"ts": row["created_at"].isoformat(), "v": row["concurrent_requests"]}
            for row in conc_series
        ],
        "drilldown_rows": drilldown_rows,
    }

    return {
        **kpis,
        "drilldown_rows": drilldown_rows,
        "drilldown_page": drilldown_page,
        "drilldown_total_pages": drilldown_total_pages,
        "drilldown_prev_url": (
            _build_page_url(request, "page", drilldown_page - 1)
            if drilldown_page > 1
            else None
        ),
        "drilldown_next_url": (
            _build_page_url(request, "page", drilldown_page + 1)
            if drilldown_page < drilldown_total_pages
            else None
        ),
        "active_page": NAV_PAGE_NAMES["api_performance"],
        "active_range": _active_range(request),
        "search": request.GET.get("search", ""),
        "selected_status": request.GET.get("status", "all"),
        "selected_method": request.GET.get("method", "all"),
        "selected_slow": request.GET.get("slow", "all"),
        "latency_series_json": json.dumps(page_data["latency_series"]),
        "scatter_json": json.dumps(page_data["scatter"]),
        "conc_series_json": json.dumps(page_data["conc_series"]),
        "page_data_json": _json_payload(page_data),
    }


def _websocket_context(request) -> dict[str, Any]:
    since = get_since(request)
    ws_agg = WebSocketEventLog.objects.filter(created_at__gte=since).aggregate(
        connects=Count("id", filter=Q(event_type="connect")),
        disconnects=Count("id", filter=Q(event_type="disconnect")),
    )
    active_conns = max(0, (ws_agg["connects"] or 0) - (ws_agg["disconnects"] or 0))
    avg_proc = round(
        WebSocketEventLog.objects.filter(
            created_at__gte=since, processing_time_ms__isnull=False
        ).aggregate(v=Avg("processing_time_ms"))["v"]
        or 0,
        1,
    )
    lifecycle = list(
        WebSocketEventLog.objects.filter(created_at__gte=since)
        .annotate(hour=TruncHour("created_at"))
        .values("hour")
        .annotate(
            connects=Count("id", filter=Q(event_type="connect")),
            disconnects=Count("id", filter=Q(event_type="disconnect")),
        )
        .order_by("hour")
    )
    consumer_msgs = list(
        WebSocketEventLog.objects.filter(created_at__gte=since)
        .values("consumer_name")
        .annotate(
            inbound=Count("id", filter=Q(event_type="receive")),
            outbound=Count("id", filter=Q(event_type="send")),
        )
        .order_by("consumer_name")
    )
    inbound = sum(row["inbound"] for row in consumer_msgs)
    outbound = sum(row["outbound"] for row in consumer_msgs)
    durations = list(
        WebSocketEventLog.objects.filter(
            event_type="disconnect",
            connection_duration_ms__isnull=False,
            created_at__gte=since,
        )
        .order_by("-created_at")
        .values_list("connection_duration_ms", flat=True)[:5000]
    )
    if durations:
        max_duration = max(durations)
        bins = 10
        counts = [0] * bins
        for value in durations:
            idx = min(bins - 1, int(value / max(max_duration, 1) * bins))
            counts[idx] += 1
        labels = [f"{round(i * max_duration / bins / 1000)}s" for i in range(bins)]
    else:
        counts = []
        labels = []

    agg_rows = {
        row["consumer_name"]: row
        for row in WebSocketEventLog.objects.filter(created_at__gte=since)
        .values("consumer_name")
        .annotate(
            connects=Count("id", filter=Q(event_type="connect")),
            disconnects=Count("id", filter=Q(event_type="disconnect")),
            avg_proc=Avg("processing_time_ms"),
            avg_msg=Avg("message_size_bytes"),
        )
        .order_by("consumer_name")
    }
    proc_times: dict[str, list[int]] = defaultdict(list)
    for consumer, ms in WebSocketEventLog.objects.filter(
        created_at__gte=since, processing_time_ms__isnull=False
    ).values_list("consumer_name", "processing_time_ms"):
        proc_times[consumer].append(ms)

    msg_counts = {
        row["consumer_name"]: (row["inbound"], row["outbound"]) for row in consumer_msgs
    }
    consumer_breakdown = []
    for name, row in agg_rows.items():
        inbound_n, outbound_n = msg_counts.get(name, (0, 0))
        consumer_breakdown.append(
            {
                "consumer": name,
                "active": max(0, (row["connects"] or 0) - (row["disconnects"] or 0)),
                "avg_proc": round(float(row["avg_proc"] or 0), 1),
                "avg_msg": round(float(row["avg_msg"])) if row["avg_msg"] else None,
                "p95_proc": _p95(proc_times[name]),
                # Fanout ratio: outbound (server->client) per inbound message.
                # High values flag broadcast-heavy consumers.
                "fanout": round(outbound_n / max(inbound_n, 1), 1),
            }
        )

    event_latency = _ws_event_latency(since)

    page_data = {
        "kpis": {
            "kpi_ws_active": active_conns,
            "kpi_ws_avg_proc": avg_proc,
            "kpi_ws_inbound": inbound,
            "kpi_ws_outbound": outbound,
        },
        "lifecycle": [
            {
                "ts": row["hour"].isoformat(),
                "connects": row["connects"],
                "disconnects": row["disconnects"],
            }
            for row in lifecycle
        ],
        "consumer_msgs": consumer_msgs,
        "duration_hist": {"labels": labels, "counts": counts},
        "consumer_breakdown": consumer_breakdown,
        "event_latency": event_latency,
    }

    return {
        "kpi_ws_active": active_conns,
        "kpi_ws_avg_proc": avg_proc,
        "kpi_ws_inbound": inbound,
        "kpi_ws_outbound": outbound,
        "consumer_breakdown": consumer_breakdown,
        "event_latency": event_latency,
        "active_page": NAV_PAGE_NAMES["websocket"],
        "active_range": _active_range(request),
        "ws_lifecycle_json": json.dumps(page_data["lifecycle"]),
        "ws_consumer_msgs_json": json.dumps(page_data["consumer_msgs"]),
        "ws_duration_hist_json": json.dumps(page_data["duration_hist"]),
        "page_data_json": _json_payload(page_data),
    }


def _system_resources_context(request) -> dict[str, Any]:
    since = get_since(request)
    active_service = request.GET.get("service", "web")
    if active_service not in _VALID_SERVICES:
        active_service = "web"

    web_series = list(
        SystemResourceSnapshot.objects.filter(
            service_type="web", captured_at__gte=since
        )
        .order_by("captured_at")
        .values(
            "captured_at",
            "cpu_percent",
            "ram_percent",
            "ram_used_mb",
            "ram_total_mb",
            "open_file_descriptors",
            "active_threads",
        )
    )
    cpu_series = web_series
    ram_series = web_series
    fds_series = web_series
    heatmap_since = timezone.now() - timedelta(days=30)
    heatmap_rows = list(
        SystemResourceSnapshot.objects.filter(
            service_type="web", captured_at__gte=heatmap_since
        )
        .annotate(dow=ExtractWeekDay("captured_at"), hour=ExtractHour("captured_at"))
        .values("dow", "hour")
        .annotate(avg_cpu=Avg("cpu_percent"))
        .order_by("dow", "hour")
    )
    heatmap = [[0.0] * 24 for _ in range(7)]
    for row in heatmap_rows:
        dow_idx = (row["dow"] - 2) % 7
        heatmap[dow_idx][row["hour"]] = float(row["avg_cpu"] or 0)

    disk_snap = (
        SystemResourceSnapshot.objects.filter(
            service_type="web", disk_used_gb__isnull=False
        )
        .order_by("-captured_at")
        .values("disk_used_gb", "disk_total_gb", "disk_percent")
        .first()
    ) or {"disk_used_gb": 0, "disk_total_gb": 100, "disk_percent": 0}

    celery_tasks = list(
        SystemResourceSnapshot.objects.filter(
            service_type="celery_worker", captured_at__gte=since
        )
        .order_by("captured_at")
        .values(
            "captured_at",
            "celery_active_tasks",
            "celery_reserved_tasks",
            "celery_queued_tasks",
        )
    )
    celery_queue = celery_tasks

    redis_series = list(
        SystemResourceSnapshot.objects.filter(
            service_type="redis", captured_at__gte=since
        )
        .order_by("captured_at")
        .values(
            "captured_at",
            "redis_used_memory_mb",
            "redis_connected_clients",
            "redis_blocked_clients",
        )
    )
    redis_mem = redis_series
    redis_clients = redis_series

    pg_conn = list(
        SystemResourceSnapshot.objects.filter(
            service_type="postgres", captured_at__gte=since
        )
        .order_by("captured_at")
        .values(
            "captured_at",
            "postgres_active_connections",
            "postgres_idle_connections",
        )
    )
    pg_size = list(
        SystemResourceSnapshot.objects.filter(
            service_type="postgres", captured_at__gte=since
        )
        .order_by("captured_at")
        .values("captured_at", "postgres_db_size_mb")
    )

    celery_queue_peak = (
        max((row["celery_queued_tasks"] or 0) for row in celery_queue)
        if celery_queue
        else 0
    )
    redis_blocked_peak = (
        max((row["redis_blocked_clients"] or 0) for row in redis_clients)
        if redis_clients
        else 0
    )
    pg_pressure_max = (
        max(
            (
                (row["postgres_active_connections"] or 0)
                / max(
                    (row["postgres_active_connections"] or 0)
                    + (row["postgres_idle_connections"] or 0),
                    1,
                )
                * 100
            )
            for row in pg_conn
        )
        if pg_conn
        else 0
    )

    page_data = {
        "active_service": active_service,
        "cpu_series": [
            {"ts": row["captured_at"].isoformat(), "v": float(row["cpu_percent"] or 0)}
            for row in cpu_series
        ],
        "ram_series": [
            {
                "ts": row["captured_at"].isoformat(),
                "pct": float(row["ram_percent"] or 0),
                "used": row["ram_used_mb"] or 0,
                "total": row["ram_total_mb"] or 0,
            }
            for row in ram_series
        ],
        "fds_series": [
            {
                "ts": row["captured_at"].isoformat(),
                "fds": row["open_file_descriptors"] or 0,
                "threads": row["active_threads"] or 0,
            }
            for row in fds_series
        ],
        "heatmap": heatmap,
        "disk_snap": _serialize(disk_snap),
        "celery_queue": [
            {"ts": row["captured_at"].isoformat(), "v": row["celery_queued_tasks"] or 0}
            for row in celery_queue
        ],
        "celery_tasks": [
            {
                "ts": row["captured_at"].isoformat(),
                "active": row["celery_active_tasks"] or 0,
                "reserved": row["celery_reserved_tasks"] or 0,
                "queued": row["celery_queued_tasks"] or 0,
            }
            for row in celery_tasks
        ],
        "redis_mem": [
            {
                "ts": row["captured_at"].isoformat(),
                "v": row["redis_used_memory_mb"] or 0,
            }
            for row in redis_mem
        ],
        "redis_clients": [
            {
                "ts": row["captured_at"].isoformat(),
                "connected": row["redis_connected_clients"] or 0,
                "blocked": row["redis_blocked_clients"] or 0,
            }
            for row in redis_clients
        ],
        "pg_conn": [
            {
                "ts": row["captured_at"].isoformat(),
                "active": row["postgres_active_connections"] or 0,
                "idle": row["postgres_idle_connections"] or 0,
            }
            for row in pg_conn
        ],
        "pg_size": [
            {"ts": row["captured_at"].isoformat(), "v": row["postgres_db_size_mb"] or 0}
            for row in pg_size
        ],
        "celery_queue_peak": celery_queue_peak,
        "redis_blocked_peak": redis_blocked_peak,
        "pg_pressure_max": round(pg_pressure_max, 1),
    }

    return {
        "active_page": NAV_PAGE_NAMES["system_resources"],
        "active_range": _active_range(request),
        "active_service": active_service,
        "disk_snap": disk_snap,
        "celery_queue_peak": celery_queue_peak,
        "redis_blocked_peak": redis_blocked_peak,
        "pg_pressure_max": round(pg_pressure_max, 1),
        "cpu_series_json": json.dumps(page_data["cpu_series"]),
        "ram_series_json": json.dumps(page_data["ram_series"]),
        "fds_series_json": json.dumps(page_data["fds_series"]),
        "heatmap_json": json.dumps(page_data["heatmap"]),
        "celery_queue_json": json.dumps(page_data["celery_queue"]),
        "celery_tasks_json": json.dumps(page_data["celery_tasks"]),
        "redis_mem_json": json.dumps(page_data["redis_mem"]),
        "redis_clients_json": json.dumps(page_data["redis_clients"]),
        "pg_conn_json": json.dumps(page_data["pg_conn"]),
        "pg_size_json": json.dumps(page_data["pg_size"]),
        "page_data_json": _json_payload(page_data),
    }


def _database_queries_context(request) -> dict[str, Any]:
    since = get_since(request)
    kpis = build_kpis(since)

    try:
        dbc_page = max(int(request.GET.get("page", "1") or 1), 1)
    except (ValueError, TypeError):
        dbc_page = 1

    base_cost_qs = (
        APIRequestLog.objects.filter(created_at__gte=since)
        .values("endpoint")
        .annotate(
            avg_queries=Avg("db_query_count"),
            max_queries=Max("db_query_count"),
            avg_db_ms=Avg("db_time_ms"),
            max_db_ms=Max("db_time_ms"),
            avg_rt_ms=Avg("response_time_ms"),
        )
        .order_by("-avg_queries")
    )
    dbc_total_count = base_cost_qs.count()
    dbc_total_pages = max(
        1, (dbc_total_count + _DB_COST_PAGE_SIZE - 1) // _DB_COST_PAGE_SIZE
    )
    dbc_page = min(dbc_page, dbc_total_pages)
    dbc_offset = (dbc_page - 1) * _DB_COST_PAGE_SIZE
    endpoint_db_cost = list(base_cost_qs[dbc_offset : dbc_offset + _DB_COST_PAGE_SIZE])
    for row in endpoint_db_cost:
        row["db_pct"] = round(
            float(row["avg_db_ms"] or 0) / max(float(row["avg_rt_ms"] or 1), 1) * 100
        )

    qcounts = list(
        APIRequestLog.objects.filter(created_at__gte=since)
        .order_by("-created_at")
        .values_list("db_query_count", flat=True)[:5000]
    )
    max_q = max(qcounts, default=1)
    bins = 12
    hist_counts = [0] * bins
    for value in qcounts:
        hist_counts[min(bins - 1, int(value / max(max_q, 1) * bins))] += 1
    hist_labels = [round(i * max_q / bins) for i in range(bins)]

    db_scatter = list(
        APIRequestLog.objects.filter(created_at__gte=since)
        .order_by("-response_time_ms")
        .values("db_time_ms", "response_time_ms")[:500]
    )
    slow_requests = list(
        APIRequestLog.objects.filter(created_at__gte=since, response_time_ms__gte=500)
        .order_by("-response_time_ms")
        .values(
            "endpoint",
            "response_time_ms",
            "db_query_count",
            "db_time_ms",
            "concurrent_requests",
        )[:12]
    )
    for row in slow_requests:
        row["db_pct"] = round(
            (row["db_time_ms"] or 0) / max(row["response_time_ms"] or 1, 1) * 100
        )

    db_offenders = _db_offenders(since)

    page_data = {
        "kpis": kpis,
        "endpoint_db_cost": endpoint_db_cost,
        "db_offenders": db_offenders,
        "db_hist": {"labels": hist_labels, "counts": hist_counts},
        "db_scatter": [
            {
                "x": row["db_time_ms"] or 0,
                "y": row["response_time_ms"] or 0,
            }
            for row in db_scatter
        ],
        "slow_requests": slow_requests,
    }

    return {
        **kpis,
        "db_offenders": db_offenders,
        "active_page": NAV_PAGE_NAMES["database_queries"],
        "active_range": _active_range(request),
        "endpoint_db_cost": endpoint_db_cost,
        "dbc_page": dbc_page,
        "dbc_total_pages": dbc_total_pages,
        "dbc_prev_url": (
            _build_page_url(request, "page", dbc_page - 1) if dbc_page > 1 else None
        ),
        "dbc_next_url": (
            _build_page_url(request, "page", dbc_page + 1)
            if dbc_page < dbc_total_pages
            else None
        ),
        "slow_requests": slow_requests,
        "db_hist_json": json.dumps(page_data["db_hist"]),
        "db_scatter_json": json.dumps(page_data["db_scatter"]),
        "page_data_json": _json_payload(page_data),
    }


def _correlation_window(request) -> tuple[datetime, datetime, str, str]:
    default_since = get_since(request)
    default_end = timezone.now()
    start = _parse_iso_datetime(request.GET.get("start", "")) or default_since
    end = _parse_iso_datetime(request.GET.get("end", "")) or default_end
    if start > end:
        start, end = default_since, default_end
    start_str = start.astimezone(timezone.get_current_timezone()).strftime(
        "%Y-%m-%dT%H:%M"
    )
    end_str = end.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%dT%H:%M")
    return start, end, start_str, end_str


def _correlation_context(request) -> dict[str, Any]:
    since = get_since(request)
    start, end, start_str, end_str = _correlation_window(request)
    available_endpoints = list(
        APIRequestLog.objects.filter(created_at__gte=since)
        .exclude(
            Q(endpoint__istartswith="/static/")
            | Q(endpoint__istartswith="/media/")
            | Q(endpoint__istartswith="/favicon")
            | Q(endpoint__iendswith=".css")
            | Q(endpoint__iendswith=".js")
            | Q(endpoint__iendswith=".ico")
            | Q(endpoint__iendswith=".png")
            | Q(endpoint__iendswith=".jpg")
            | Q(endpoint__iendswith=".jpeg")
            | Q(endpoint__iendswith=".svg")
            | Q(endpoint__iendswith=".woff")
            | Q(endpoint__iendswith=".woff2")
            | Q(endpoint__iendswith=".ttf")
            | Q(endpoint__iendswith=".map")
            | Q(endpoint__iendswith=".txt")
            | Q(endpoint__iendswith=".xml")
        )
        .values_list("endpoint", flat=True)
        .distinct()
        .order_by("endpoint")
    )
    selected_endpoint = request.GET.get(
        "endpoint", available_endpoints[0] if available_endpoints else ""
    )

    p99_series = list(
        PerformanceSummary.objects.filter(
            log_type="api",
            endpoint_or_consumer=selected_endpoint,
            window_start__gte=start,
            window_start__lte=end,
        )
        .order_by("window_start")
        .values("window_start", "p99_ms")
    )
    cpu_series = list(
        SystemResourceSnapshot.objects.filter(
            service_type="web",
            captured_at__gte=start,
            captured_at__lte=end,
        )
        .order_by("captured_at")
        .values("captured_at", "cpu_percent", "ram_percent")
    )
    cel_series = list(
        SystemResourceSnapshot.objects.filter(
            service_type="celery_worker",
            captured_at__gte=start,
            captured_at__lte=end,
        )
        .order_by("captured_at")
        .values("captured_at", "celery_queued_tasks")
    )
    kpis = build_kpis(start)
    corr_timeline = list(
        APIRequestLog.objects.filter(
            endpoint=selected_endpoint,
            created_at__gte=start,
            created_at__lte=end,
        )
        .order_by("-created_at")
        .values(
            "created_at",
            "method",
            "endpoint",
            "status_code",
            "response_time_ms",
            "db_query_count",
            "db_time_ms",
            "concurrent_requests",
        )[:12]
    )

    corr_chart = {
        "p99": [
            {"ts": row["window_start"].isoformat(), "v": row["p99_ms"]}
            for row in p99_series
        ],
        "cpu": [
            {"ts": row["captured_at"].isoformat(), "v": float(row["cpu_percent"] or 0)}
            for row in cpu_series
        ],
        "ram": [
            {"ts": row["captured_at"].isoformat(), "v": float(row["ram_percent"] or 0)}
            for row in cpu_series
        ],
        "celery": [
            {"ts": row["captured_at"].isoformat(), "v": row["celery_queued_tasks"] or 0}
            for row in cel_series
        ],
    }
    page_data = {
        "kpis": kpis,
        "available_endpoints": available_endpoints,
        "selected_endpoint": selected_endpoint,
        "corr_chart": corr_chart,
        "corr_timeline": corr_timeline,
        "selected_start": start_str,
        "selected_end": end_str,
    }

    return {
        **kpis,
        "active_page": NAV_PAGE_NAMES["correlation"],
        "active_range": _active_range(request),
        "available_endpoints": available_endpoints,
        "selected_endpoint": selected_endpoint,
        "selected_start": start_str,
        "selected_end": end_str,
        "corr_chart_json": json.dumps(corr_chart),
        "corr_timeline": corr_timeline,
        "page_data_json": _json_payload(page_data),
    }


def _raw_logs_context(request) -> dict[str, Any]:
    since = get_since(request)
    raw_api_rows, _, _ = _api_drilldown_rows(request, since, limit=18)

    ws_qs = WebSocketEventLog.objects.filter(created_at__gte=since).order_by(
        "-created_at"
    )
    selected_ws_consumer = request.GET.get("consumer", "all")
    selected_ws_event = request.GET.get("event", "all")
    if selected_ws_consumer != "all":
        ws_qs = ws_qs.filter(consumer_name=selected_ws_consumer)
    if selected_ws_event != "all":
        ws_qs = ws_qs.filter(event_type=selected_ws_event)

    raw_ws_rows = list(
        ws_qs.values(
            "created_at",
            "consumer_name",
            "event_type",
            "direction",
            "message_size_bytes",
            "processing_time_ms",
            "connection_duration_ms",
        )[:18]
    )
    ws_consumers = list(
        WebSocketEventLog.objects.filter(created_at__gte=since)
        .values_list("consumer_name", flat=True)
        .distinct()
        .order_by("consumer_name")
    )
    page_data = {
        "raw_api_rows": raw_api_rows,
        "raw_ws_rows": raw_ws_rows,
        "ws_consumers": ws_consumers,
        "selected_ws_consumer": selected_ws_consumer,
        "selected_ws_event": selected_ws_event,
    }

    return {
        "active_page": NAV_PAGE_NAMES["raw_logs"],
        "active_range": _active_range(request),
        "raw_api_rows": raw_api_rows,
        "raw_ws_rows": raw_ws_rows,
        "ws_consumers": ws_consumers,
        "selected_search": request.GET.get("search", ""),
        "selected_status": request.GET.get("status", "all"),
        "selected_method": request.GET.get("method", "all"),
        "selected_slow": request.GET.get("slow", "all"),
        "selected_ws_consumer": selected_ws_consumer,
        "selected_ws_event": selected_ws_event,
        "page_data_json": _json_payload(page_data),
    }


@require_safe
@staff_member_required
def dashboard_overview(request):
    return render(
        request,
        "performance/dashboard/overview.html",
        _overview_context(request),
    )


@require_safe
@staff_member_required
def dashboard_api_performance(request):
    return render(
        request,
        "performance/dashboard/api_performance.html",
        _api_performance_context(request),
    )


@require_safe
@staff_member_required
def dashboard_websocket(request):
    return render(
        request,
        "performance/dashboard/websocket.html",
        _websocket_context(request),
    )


@require_safe
@staff_member_required
def dashboard_system_resources(request):
    return render(
        request,
        "performance/dashboard/system_resources.html",
        _system_resources_context(request),
    )


@require_safe
@staff_member_required
def dashboard_database_queries(request):
    return render(
        request,
        "performance/dashboard/database_queries.html",
        _database_queries_context(request),
    )


@require_safe
@staff_member_required
def dashboard_correlation(request):
    return render(
        request,
        "performance/dashboard/correlation.html",
        _correlation_context(request),
    )


@require_safe
@staff_member_required
def dashboard_raw_logs(request):
    return render(
        request,
        "performance/dashboard/raw_logs.html",
        _raw_logs_context(request),
    )


@require_safe
@staff_member_required
def api_overview_data(request):
    return JsonResponse(_serialize(_overview_context(request)))


@require_safe
@staff_member_required
def api_api_performance_data(request):
    return JsonResponse(_serialize(_api_performance_context(request)))


@require_safe
@staff_member_required
def api_websocket_data(request):
    return JsonResponse(_serialize(_websocket_context(request)))


@require_safe
@staff_member_required
def api_resources_data(request):
    return JsonResponse(_serialize(_system_resources_context(request)))


@require_safe
@staff_member_required
def api_db_data(request):
    return JsonResponse(_serialize(_database_queries_context(request)))


@require_safe
@staff_member_required
def api_correlation_data(request):
    return JsonResponse(_serialize(_correlation_context(request)))


@require_safe
@staff_member_required
def api_raw_logs_data(request):
    return JsonResponse(_serialize(_raw_logs_context(request)))
