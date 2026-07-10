"""Settings-driven thresholds and branding for performance reports.

No magic numbers live in the builders. Every threshold, SLO band and brand
string is sourced from here, which in turn reads ``settings.PERFORMANCE_REPORTS``
(falling back to defaults that mirror the dashboard's scale-recommendation
bands in ``dashboard/views.py``).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

# Defaults intentionally mirror the dashboard's own thresholds so a report and
# the live dashboard never disagree about what "amber" or "within SLA" means.
_DEFAULTS: dict[str, Any] = {
    # Branding / masthead (overridable via settings.PERFORMANCE_REPORTS, which
    # in turn reads from .env — see PERFORMANCE_REPORT_* keys).
    "BRAND_NAME": "Ping Prod Communication Platform",
    "BRAND_SUB": "Communication Service · Performance Engineering",
    "ENVIRONMENT": "Production",
    "CLASSIFICATION": "Confidential — For Authorised Recipient Only",
    "REVISION": "Rev C",
    # Latency / SLA.
    "SLA_MS": 300,  # matches dashboard SLA_THRESHOLD_MS
    "APDEX_T_MS": 300,
    "P99_AMBER_MS": 250,
    "P99_RED_MS": 500,
    # Throughput / concurrency.
    "CONC_AMBER": 30,
    "CONC_RED": 50,
    # The connection-pool *size* is NOT in the DB (handoff §4). Left None so the
    # pool-utilisation % is omitted unless an operator supplies a real number.
    "DB_POOL_SIZE": None,
    "POOL_WARN_PCT": 85,
    # Database.
    "DBQ_AMBER": 6,
    "DBQ_RED": 10,
    "DB_TIME_PCT_RED": 50,
    "SLOW_MS": 500,
    # Resources.
    "CPU_WARN_PCT": 60,
    "CPU_CRIT_PCT": 80,
    "RAM_WARN_PCT": 70,
    "RAM_CRIT_PCT": 85,
    # Curated bottleneck resolution status (handoff §5). Default empty -> the
    # status column is omitted and the report says status is uncurated.
    "BOTTLENECK_STATUS": {},
    # Email.
    "REPORT_FROM_EMAIL": None,  # falls back to settings.SMTP_SENDER_EMAIL
}


def get_report_config() -> dict[str, Any]:
    """Merged report config: defaults overlaid with ``PERFORMANCE_REPORTS``."""
    merged = dict(_DEFAULTS)
    user_cfg = getattr(settings, "PERFORMANCE_REPORTS", {}) or {}
    if isinstance(user_cfg, dict):
        merged.update(user_cfg)
    return merged
