"""Constructor-based report data builders.

One builder per report. Each takes the resolved ``(start, end)`` window in its
constructor and exposes a single ``build()`` returning a plain dict of
primitives/lists/dicts ready for the template. All numbers are
sampling-corrected: builders reuse the dashboard's ``_weight()`` /
``build_kpis`` helpers rather than counting raw rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db.models import Avg, Count, Max, Q, Sum
from django.utils import timezone

from django_perfy.dashboard.views import (
    _db_offenders,
    _error_by_status,
    _scale_recommendations,
    _traffic_series,
    _weight,
    _wmul,
    build_kpis,
)
from django_perfy.models import (
    APIRequestLog,
    PerformanceSummary,
    SystemResourceSnapshot,
)

from . import charts
from .config import get_report_config
from .ranges import range_label

# Colour bands shared with the dashboard's green/amber/red language.
_GREEN = "#16a34a"
_AMBER = "#d97706"
_RED = "#b91c1c"
_BLUE = "#1d4ed8"
_INDIGO = "#4f46e5"
_TEAL = "#0d9488"

_STATUS_LABELS = {
    400: "400 Bad Request",
    401: "401 Unauthorized",
    403: "403 Forbidden",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
    409: "409 Conflict",
    422: "422 Unprocessable",
    429: "429 Too Many Requests",
    500: "500 Server Error",
    502: "502 Bad Gateway",
    503: "503 Unavailable",
    504: "504 Gateway Timeout",
}
_ERROR_COLORS = ["#1d4ed8", "#3b82f6", "#60a5fa", "#93c5fd", "#b91c1c", "#f87171"]


def _short(endpoint: str, width: int = 18) -> str:
    """A compact label for charts (last path segment-ish)."""
    text = (endpoint or "").strip("/")
    parts = [p for p in text.split("/") if p and "<" not in p]
    label = parts[-1] if parts else (text or "root")
    return label[:width]


class BaseReportBuilder:
    """Shared window handling, config and masthead context."""

    code: str = "PTR"
    title: str = "Performance Report"
    eyebrow: str = "Performance"
    basis: str = "RED · Apdex"
    audience: str = "Backend · SRE"

    def __init__(
        self,
        start: datetime | None,
        end: datetime,
        *,
        range_key: str | None = None,
        **overrides: Any,
    ) -> None:
        self.start = start
        self.end = end
        self.range_key = range_key
        self.cfg = get_report_config()
        if overrides:
            self.cfg = {**self.cfg, **overrides}

    # -- window helpers ----------------------------------------------------- #
    def effective_since(self) -> datetime:
        """Lower bound for queries. For ``all`` falls back to earliest log."""
        if self.start is not None:
            return self.start
        earliest = (
            APIRequestLog.objects.order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        return earliest or (self.end - timedelta(days=1))

    @property
    def window_seconds(self) -> float:
        return max((self.end - self.effective_since()).total_seconds(), 1.0)

    @property
    def document_id(self) -> str:
        return f"{self.code}-{self.end:%Y-%m%d}"

    def period_label(self) -> str:
        if self.start is None:
            return f"All time → {self.end:%d %b %Y}"
        return f"{self.start:%d %b} – {self.end:%d %b %Y}"

    def masthead(self) -> dict[str, Any]:
        return {
            "brand_name": self.cfg["BRAND_NAME"],
            "brand_sub": self.cfg["BRAND_SUB"],
            "environment": self.cfg["ENVIRONMENT"],
            "classification": self.cfg["CLASSIFICATION"],
            "revision": self.cfg["REVISION"],
            "code": self.code,
            "title": self.title,
            "eyebrow": self.eyebrow,
            "basis": self.basis,
            "audience": self.audience,
            "document_id": self.document_id,
            "period_label": self.period_label(),
            "range_label": range_label(self.range_key) if self.range_key else "",
            "generated": f"{timezone.localtime(self.end):%d %b %Y %H:%M}",
        }

    def build(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# PTR-LAT — Latency & cost                                                     #
# --------------------------------------------------------------------------- #
class LatencyReportBuilder(BaseReportBuilder):
    code: str = "PTR-LAT"
    title: str = "API Latency & Cost Insight"
    eyebrow: str = "Latency & Cost"

    def __init__(self, start, end, *, apdex_t_ms: int | None = None, **kw) -> None:
        super().__init__(start, end, **kw)
        self.apdex_t = int(apdex_t_ms or self.cfg["APDEX_T_MS"])

    def _endpoint_rows(self, since: datetime) -> list[dict[str, Any]]:
        t: int = self.apdex_t
        # Per-endpoint weighted request metrics from raw logs.
        raw: dict[str, Any] = {
            row["endpoint"]: row
            for row in APIRequestLog.objects.filter(created_at__gte=since)
            .values("endpoint")
            .annotate(
                w=Sum(_weight()),
                w_sat=Sum(_weight(), filter=Q(response_time_ms__lte=t)),
                w_tol=Sum(
                    _weight(),
                    filter=Q(response_time_ms__gt=t, response_time_ms__lte=4 * t),
                ),
                w_under_sla=Sum(
                    _weight(), filter=Q(response_time_ms__lt=self.cfg["SLA_MS"])
                ),
                w_rt=Sum(_wmul("response_time_ms")),
                w_dbt=Sum(_wmul("db_time_ms")),
                w_dbq=Sum(_wmul("db_query_count")),
                w_egress=Sum(_wmul("response_size_bytes")),
            )
        }
        # Per-endpoint percentiles from pre-aggregated summaries.
        pct: dict[str, Any] = {
            row["endpoint_or_consumer"]: row
            for row in PerformanceSummary.objects.filter(
                log_type="api", window_start__gte=since
            )
            .values("endpoint_or_consumer")
            .annotate(
                p50=Avg("p50_ms"),
                p95=Avg("p95_ms"),
                p99=Avg("p99_ms"),
                reqs=Sum("total_requests"),
            )
        }

        rows: list[dict[str, Any]] = []
        for endpoint, r in raw.items():
            w = float(r["w"] or 0.0) or 1.0
            p = pct.get(endpoint, {})
            p50 = round(float(p.get("p50") or 0))
            p95 = round(float(p.get("p95") or 0))
            p99 = round(float(p.get("p99") or 0))
            rt = float(r["w_rt"] or 0.0)
            dbt = float(r["w_dbt"] or 0.0)
            sat = float(r["w_sat"] or 0.0)
            tol = float(r["w_tol"] or 0.0)
            rows.append(
                {
                    "endpoint": endpoint,
                    "short": _short(endpoint),
                    "weight": w,
                    "requests": round(w),
                    "p50": p50,
                    "p95": p95,
                    "p99": p99,
                    "tail_spread": round(p99 / p50, 1) if p50 else 0.0,
                    "avg_db_queries": round(float(r["w_dbq"] or 0.0) / w, 1),
                    "avg_db_ms": round(dbt / w),
                    "db_pct": round(dbt / rt * 100) if rt else 0,
                    "est_db_ms": round(dbt),
                    "compute_h": round(rt / 1000 / 3600, 1),
                    "db_h": round(dbt / 1000 / 3600, 1),
                    "egress_mb": round(float(r["w_egress"] or 0.0) / 1_000_000, 1),
                    "apdex": round((sat + tol / 2) / w, 2),
                    "within_sla": round(float(r["w_under_sla"] or 0.0) / w * 100, 1),
                }
            )

        total_req = sum(r["weight"] for r in rows) or 1.0
        total_db = sum(r["est_db_ms"] for r in rows) or 1.0
        max_p95 = max((r["p95"] for r in rows), default=1) or 1
        ref_p95: int = self.cfg["P99_RED_MS"] or 500
        for r in rows:
            r["traffic_share"] = round(r["weight"] / total_req * 100, 1)
            r["db_share"] = round(r["est_db_ms"] / total_db * 100, 1)
            r["tail_sev"] = charts.clamp(r["p95"] / ref_p95, 0, 1.5)
        max_tail = max((r["tail_sev"] for r in rows), default=1) or 1
        raw_priority: list[float] = []
        for r in rows:
            raw_pi = (
                0.30 * (r["weight"] / total_req)
                + 0.35 * (r["tail_sev"] / max_tail)
                + 0.35 * (r["est_db_ms"] / total_db)
            )
            r["_raw_pi"] = raw_pi
            raw_priority.append(raw_pi)
        max_pi = max(raw_priority, default=1) or 1
        for r in rows:
            r["priority"] = round(r["_raw_pi"] / max_pi * 100)
            r["max_p95"] = max_p95
        rows.sort(key=lambda r: r["priority"], reverse=True)
        return rows

    def build(self) -> dict[str, Any]:
        since = self.effective_since()
        kpis = build_kpis(since)
        rows = self._endpoint_rows(since)
        has_data: bool = bool(rows) and kpis["kpi_total_requests"] > 0

        # Overall Apdex from weighted satisfied/tolerating counts.
        t: int = self.apdex_t
        agg = APIRequestLog.objects.filter(created_at__gte=since).aggregate(
            w=Sum(_weight()),
            w_sat=Sum(_weight(), filter=Q(response_time_ms__lte=t)),
            w_tol=Sum(
                _weight(),
                filter=Q(response_time_ms__gt=t, response_time_ms__lte=4 * t),
            ),
        )
        w = float(agg["w"] or 0.0) or 1.0
        apdex = round((float(agg["w_sat"] or 0) + float(agg["w_tol"] or 0) / 2) / w, 2)
        apdex_color: str = (
            _GREEN if apdex >= 0.94 else _AMBER if apdex >= 0.85 else _RED
        )

        max_p95 = max((r["p95"] for r in rows), default=1) or 1
        max_traffic = max((r["traffic_share"] for r in rows), default=1) or 1
        bubbles: list[dict[str, Any]] = [
            {
                "x": r["traffic_share"] / max_traffic,
                "y": charts.clamp(r["p95"] / max_p95, 0, 1),
                "r": 6 + charts.clamp(r["db_share"] / 100, 0, 1) * 26,
                "color": (
                    _RED if r["db_pct"] >= self.cfg["DB_TIME_PCT_RED"] else _INDIGO
                ),
                "label": r["short"],
            }
            for r in rows[:8]
        ]

        return {
            **self.masthead(),
            "has_data": has_data,
            "apdex_t": t,
            "sla_ms": self.cfg["SLA_MS"],
            "kpi_p50": kpis["kpi_p50_ms"],
            "kpi_p95": kpis["kpi_p95_ms"],
            "kpi_p99": kpis["kpi_p99_ms"],
            "kpi_sla_pct": kpis["kpi_sla_pct"],
            "kpi_avg_rt": kpis["kpi_avg_rt"],
            "apdex": apdex,
            "apdex_color": apdex_color,
            "apdex_gauge": charts.ring(apdex * 100, apdex_color, size=132, stroke=13),
            "rows": rows[:12],
            "bubble_svg": charts.bubble_svg(
                bubbles,
                xlabel="traffic share →",
                ylabel="p95 latency (ms)",
                x_max=max_traffic,
                y_max=max_p95,
                x_suffix="%",
                y_suffix="",
                threshold_frac=charts.clamp(self.cfg["SLA_MS"] / max_p95, 0, 1),
                threshold_label=f"SLA {self.cfg['SLA_MS']} ms",
            ),
            "top_offender": rows[0] if rows else None,
        }


# --------------------------------------------------------------------------- #
# PTR-THR — Throughput & capacity                                              #
# --------------------------------------------------------------------------- #
class ThroughputReportBuilder(BaseReportBuilder):
    code: str = "PTR-THR"
    title: str = "Throughput & Capacity"
    eyebrow: str = "Throughput & Capacity"
    basis: str = "RED · Golden Signals"

    def _concurrency(self, since: datetime) -> dict[str, Any]:
        agg = APIRequestLog.objects.filter(created_at__gte=since).aggregate(
            mean=Avg("concurrent_requests"), peak=Max("concurrent_requests")
        )
        # P95 from a capped sample (concurrency isn't pre-aggregated).
        values = sorted(
            APIRequestLog.objects.filter(created_at__gte=since)
            .order_by("-created_at")
            .values_list("concurrent_requests", flat=True)[:20000]
        )
        p95: int = 0
        if values:
            idx = min(len(values) - 1, int(len(values) * 0.95))
            p95 = values[idx]
        return {
            "mean": round(float(agg["mean"] or 0), 1),
            "p95": p95,
            "peak": int(agg["peak"] or 0),
        }

    def _endpoint_rows(self, since: datetime) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {
            row["endpoint_or_consumer"]: {
                "endpoint": row["endpoint_or_consumer"],
                "requests": int(row["reqs"] or 0),
                "errors": int(row["errs"] or 0),
                "peak_minute": int(row["peak_minute"] or 0),
            }
            for row in PerformanceSummary.objects.filter(
                log_type="api", window_start__gte=since
            )
            .values("endpoint_or_consumer")
            .annotate(
                reqs=Sum("total_requests"),
                errs=Sum("error_count"),
                peak_minute=Max("total_requests"),
            )
        }
        out = list(rows.values())
        total = sum(r["requests"] for r in out) or 1
        for r in out:
            r["mean_tps"] = round(r["requests"] / self.window_seconds, 2)
            # Peak TPS ≈ busiest single summary window's rate (60s minute window).
            r["peak_tps"] = round(r["peak_minute"] / 60, 1)
            r["share"] = round(r["requests"] / total * 100, 1)
            r["err_pct"] = round(r["errors"] / max(r["requests"], 1) * 100, 2)
        out.sort(key=lambda r: r["requests"], reverse=True)
        return out[:10]

    def build(self) -> dict[str, Any]:
        since = self.effective_since()
        kpis = build_kpis(since)
        traffic = _traffic_series(since)
        conc = self._concurrency(since)
        rows = self._endpoint_rows(since)
        has_data: bool = kpis["kpi_total_requests"] > 0

        counts: list[float] = [row["count"] for row in traffic]
        peak_rps = round(max(counts, default=0) / 60, 1)  # busiest bucket
        mean_rps = round(kpis["kpi_throughput_rpm"] / 60, 2)
        success_rate = round(100 - kpis["kpi_error_rate"], 2)

        pool_size: int | None = self.cfg["DB_POOL_SIZE"]
        pool_pct: int | None = (
            round(conc["peak"] / pool_size * 100) if pool_size else None
        )
        pool_color: str = _GREEN
        if pool_pct is not None:
            pool_color = (
                _RED
                if pool_pct > self.cfg["POOL_WARN_PCT"]
                else _AMBER if pool_pct > 70 else _GREEN
            )

        errors = _error_by_status(since)
        segments: list[tuple[int, str]] = [
            (row["count"], _ERROR_COLORS[i % len(_ERROR_COLORS)])
            for i, row in enumerate(errors)
        ]
        error_rows: list[dict[str, Any]] = [
            {
                "label": _STATUS_LABELS.get(
                    row["status_code"], str(row["status_code"])
                ),
                "count": row["count"],
                "color": _ERROR_COLORS[i % len(_ERROR_COLORS)],
            }
            for i, row in enumerate(errors)
        ]

        slo_table: list[dict[str, Any]] = [
            {
                "objective": "Success rate",
                "target": "≥ 99.5%",
                "observed": f"{success_rate}%",
                "pass": success_rate >= 99.5,
            },
            {
                "objective": "Error rate (4xx+5xx)",
                "target": "< 0.5%",
                "observed": f"{kpis['kpi_error_rate']}%",
                "pass": kpis["kpi_error_rate"] < 0.5,
            },
            {
                "objective": "Peak concurrency band",
                "target": f"≤ {self.cfg['CONC_AMBER']}",
                "observed": str(conc["peak"]),
                "pass": conc["peak"] <= self.cfg["CONC_AMBER"],
            },
        ]
        if pool_pct is not None:
            slo_table.append(
                {
                    "objective": "Peak concurrency vs pool",
                    "target": f"< {self.cfg['POOL_WARN_PCT']}%",
                    "observed": f"{pool_pct}% ({conc['peak']}/{pool_size})",
                    "pass": pool_pct < self.cfg["POOL_WARN_PCT"],
                }
            )

        return {
            **self.masthead(),
            "has_data": has_data,
            "mean_rps": mean_rps,
            "peak_rps": peak_rps,
            "total_requests": kpis["kpi_total_requests"],
            "peak_conc": conc["peak"],
            "mean_conc": conc["mean"],
            "p95_conc": conc["p95"],
            "success_rate": success_rate,
            "error_rate": kpis["kpi_error_rate"],
            "pool_size": pool_size,
            "pool_pct": pool_pct,
            "pool_color": pool_color,
            "pool_gauge": (
                charts.ring(pool_pct or 0, pool_color, size=120, stroke=12)
                if pool_pct is not None
                else ""
            ),
            "success_gauge": charts.ring(success_rate, _GREEN, size=120, stroke=12),
            "rows": rows,
            "throughput_svg": charts.area_svg(
                [row["count"] / 60 for row in traffic],
                _TEAL,
                xlabels=[row["ts"][5:16].replace("T", " ") for row in traffic],
                fill_id="thrFill",
            ),
            "error_donut": charts.donut(segments) if segments else "",
            "error_rows": error_rows,
        }


# --------------------------------------------------------------------------- #
# PTR-RES — Resource utilisation                                               #
# --------------------------------------------------------------------------- #
class ResourceReportBuilder(BaseReportBuilder):
    code: str = "PTR-RES"
    title: str = "Resource Utilization Under Load"
    eyebrow: str = "Resource Utilization"
    basis: str = "ISO 25010 · Resource Utilization"

    _TIERS = ["web", "celery_worker", "redis", "postgres"]
    _EXTRA = {
        "postgres": ["postgres_active_connections", "postgres_db_size_mb"],
        "redis": ["redis_used_memory_mb", "redis_connected_clients"],
        "celery_worker": ["celery_queued_tasks", "celery_active_tasks"],
        "web": ["open_file_descriptors", "active_threads"],
    }

    def _tier_rows(self, since: datetime) -> list[dict[str, Any]]:
        rows = []
        for tier in self._TIERS:
            qs = SystemResourceSnapshot.objects.filter(
                service_type=tier, captured_at__gte=since
            )
            agg = qs.aggregate(
                cpu_mean=Avg("cpu_percent"),
                cpu_peak=Max("cpu_percent"),
                ram_mean=Avg("ram_percent"),
                ram_peak=Max("ram_percent"),
                samples=Count("id"),
            )
            if not agg["samples"]:
                continue
            extra: dict[str, dict[str, float]] = {}
            for field in self._EXTRA.get(tier, []):
                vals = qs.aggregate(mean=Avg(field), peak=Max(field))
                extra[field] = {
                    "mean": round(float(vals["mean"] or 0), 1),
                    "peak": round(float(vals["peak"] or 0), 1),
                }
            rows.append(
                {
                    "tier": tier,
                    "label": tier.replace("_", " ").title(),
                    "cpu_mean": round(float(agg["cpu_mean"] or 0), 1),
                    "cpu_peak": round(float(agg["cpu_peak"] or 0), 1),
                    "ram_mean": round(float(agg["ram_mean"] or 0), 1),
                    "ram_peak": round(float(agg["ram_peak"] or 0), 1),
                    "samples": agg["samples"],
                    "extra": extra,
                }
            )
        return rows

    def build(self) -> dict[str, Any]:
        since = self.effective_since()
        tiers = self._tier_rows(since)
        web_series = list(
            SystemResourceSnapshot.objects.filter(
                service_type="web", captured_at__gte=since
            )
            .order_by("captured_at")
            .values_list("captured_at", "cpu_percent", "ram_percent")
        )
        has_data: bool = bool(tiers)

        cpu_warn, cpu_crit = self.cfg["CPU_WARN_PCT"], self.cfg["CPU_CRIT_PCT"]
        ram_warn, ram_crit = self.cfg["RAM_WARN_PCT"], self.cfg["RAM_CRIT_PCT"]
        web = next((t for t in tiers if t["tier"] == "web"), None)
        peak_cpu: float = web["cpu_peak"] if web else 0.0
        peak_ram: float = web["ram_peak"] if web else 0.0

        # Binding constraint: closest metric to (or over) its threshold.
        candidates: list[tuple[str, float, int]] = [
            ("Web CPU", peak_cpu, cpu_crit),
            ("Web RAM", peak_ram, ram_crit),
        ]
        binding: dict[str, Any] | None = None
        best_gap: float | None = None
        for name, value, limit in candidates:
            gap: float = limit - value
            if best_gap is None or gap < best_gap:
                best_gap = gap
                binding = {
                    "name": name,
                    "value": value,
                    "limit": limit,
                    "near": gap <= 5,
                    "over": value >= limit,
                }

        cpu_color = (
            _RED if peak_cpu >= cpu_crit else _AMBER if peak_cpu >= cpu_warn else _GREEN
        )
        ram_color = (
            _RED if peak_ram >= ram_crit else _AMBER if peak_ram >= ram_warn else _GREEN
        )

        return {
            **self.masthead(),
            "has_data": has_data,
            "tiers": tiers,
            "peak_cpu": peak_cpu,
            "peak_ram": peak_ram,
            "cpu_color": cpu_color,
            "ram_color": ram_color,
            "cpu_gauge": charts.ring(peak_cpu, cpu_color, size=120, stroke=12),
            "ram_gauge": charts.ring(peak_ram, ram_color, size=120, stroke=12),
            "binding": binding,
            "thresholds": {
                "cpu_warn": cpu_warn,
                "cpu_crit": cpu_crit,
                "ram_warn": ram_warn,
                "ram_crit": ram_crit,
            },
            "cpu_svg": charts.area_svg(
                [float(c or 0) for _, c, _ in web_series],
                _AMBER,
                ymax=100,
                threshold=cpu_crit,
                threshold_label=f"critical {cpu_crit}%",
                xlabels=[f"{ts:%d %b %H:%M}" for ts, _, _ in web_series],
                fill_id="cpuFill",
            ),
            "ram_svg": charts.area_svg(
                [float(r or 0) for _, _, r in web_series],
                "#a78bfa",
                ymax=100,
                threshold=ram_crit,
                threshold_label=f"critical {ram_crit}%",
                xlabels=[f"{ts:%d %b %H:%M}" for ts, _, _ in web_series],
                fill_id="ramFill",
            ),
        }


# --------------------------------------------------------------------------- #
# PTR-BNK — Bottleneck analysis                                                #
# --------------------------------------------------------------------------- #
class BottleneckReportBuilder(BaseReportBuilder):
    code: str = "PTR-BNK"
    title: str = "Bottleneck Analysis & Root-Cause"
    eyebrow: str = "Root-Cause"
    basis: str = "RED · Scale bands"

    def _severity(self, db_pct: int, avg_q: float) -> tuple[str, str, str]:
        """(level, css, color) from the dashboard scale bands."""
        if db_pct > self.cfg["DB_TIME_PCT_RED"] or avg_q > self.cfg["DBQ_RED"]:
            return "P1", "p1", _RED
        if avg_q > self.cfg["DBQ_AMBER"]:
            return "P2", "p2", _AMBER
        return "P3", "p3", _BLUE

    def build(self) -> dict[str, Any]:
        since = self.effective_since()
        kpis = build_kpis(since)
        scale = _scale_recommendations(kpis)
        offenders = _db_offenders(since)
        status_map = self.cfg.get("BOTTLENECK_STATUS") or {}
        status_curated = bool(status_map)

        # Per-endpoint DB-bound %, to grade severity.
        dbpct: dict[str, int] = {
            row["endpoint"]: round(
                float(row["avg_db_ms"] or 0)
                / max(float(row["avg_rt_ms"] or 1), 1)
                * 100
            )
            for row in APIRequestLog.objects.filter(created_at__gte=since)
            .values("endpoint")
            .annotate(avg_db_ms=Avg("db_time_ms"), avg_rt_ms=Avg("response_time_ms"))
        }

        findings: list[dict[str, Any]] = []
        for i, off in enumerate(offenders, start=1):
            ep: str = off["endpoint"]
            db_pct = dbpct.get(ep, 0)
            avg_q: float = off["avg_db_queries"]
            level, css, color = self._severity(db_pct, avg_q)
            fid: str = f"{self.code}-F{i:02d}"
            findings.append(
                {
                    "id": fid,
                    "endpoint": ep,
                    "short": _short(ep),
                    "est_db_ms": off["est_total_db_ms"],
                    "share_pct": off["share_pct"],
                    "avg_db_queries": avg_q,
                    "db_pct": db_pct,
                    "level": level,
                    "sev_css": css,
                    "sev_color": color,
                    "status": status_map.get(fid) if status_curated else None,
                }
            )

        slow_requests = list(
            APIRequestLog.objects.filter(
                created_at__gte=since, response_time_ms__gte=self.cfg["SLOW_MS"]
            )
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

        # Impact (DB share) vs effort (query-count proxy) bubble matrix.
        max_q = max((f["avg_db_queries"] for f in findings), default=1) or 1
        max_share = max((f["share_pct"] for f in findings), default=1) or 1
        bubbles = [
            {
                "x": charts.clamp(f["avg_db_queries"] / max_q, 0.04, 1),
                "y": charts.clamp(f["share_pct"] / max_share, 0, 1),
                "r": 6 + charts.clamp(f["share_pct"] / max_share, 0, 1) * 24,
                "color": f["sev_color"],
                "label": f["short"],
            }
            for f in findings[:8]
        ]

        counts = {"P1": 0, "P2": 0, "P3": 0}
        for f in findings:
            counts[f["level"]] = counts.get(f["level"], 0) + 1

        return {
            **self.masthead(),
            "has_data": bool(findings),
            "findings": findings,
            "slow_requests": slow_requests,
            "status_curated": status_curated,
            "counts": counts,
            "total_findings": len(findings),
            "scale": scale,
            "kpi_p99": kpis["kpi_p99_ms"],
            "kpi_avg_dbq": kpis["kpi_avg_dbq"],
            "kpi_db_pct": kpis["kpi_db_pct"],
            "matrix_svg": charts.bubble_svg(
                bubbles,
                xlabel="effort (queries / request) →",
                ylabel="impact (share of DB time)",
                x_max=max_q,
                y_max=max_share,
                x_suffix="",
                y_suffix="%",
            ),
        }
