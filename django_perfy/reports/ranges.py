"""Date-range resolution for reports.

One resolver maps a range key to a timezone-aware ``(start, end)`` window with
``end = now()``. ``all`` resolves to ``(None, now)`` — an open lower bound.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

# Single source of truth for the allow-list. ``all`` is handled specially.
RANGE_DELTAS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
VALID_RANGES: frozenset[str] = frozenset(set(RANGE_DELTAS) | {"all"})

_RANGE_LABELS: dict[str, str] = {
    "1h": "Last 1 hour",
    "6h": "Last 6 hours",
    "24h": "Last 24 hours",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "all": "All time",
}

# Per the handoff: 1h/6h read minute-grain summaries, everything else hour-grain.
_MINUTE_GRAIN = {"1h", "6h"}


def resolve_range(range_key: str) -> tuple[datetime | None, datetime]:
    """Resolve a range key to a ``(start, end)`` UTC-aware window.

    Raises ``ValueError`` for anything outside the allow-list so callers can
    return a 400 instead of silently defaulting.
    """
    if range_key not in VALID_RANGES:
        raise ValueError(f"invalid range: {range_key!r}")
    end = timezone.now()
    if range_key == "all":
        return None, end
    return end - RANGE_DELTAS[range_key], end


def range_label(range_key: str) -> str:
    return _RANGE_LABELS.get(range_key, range_key)


def summary_granularity(range_key: str) -> str:
    """Preferred ``PerformanceSummary.granularity`` for a range key."""
    return "minute" if range_key in _MINUTE_GRAIN else "hour"
