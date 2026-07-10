"""Declarative report registry.

Adding a 5th report later is a one-line addition here plus a builder + template.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from .builders import (
    BaseReportBuilder,
    BottleneckReportBuilder,
    LatencyReportBuilder,
    ResourceReportBuilder,
    ThroughputReportBuilder,
)


@dataclass(frozen=True)
class ReportSpec:
    code: str
    title: str
    template: str
    builder: Type[BaseReportBuilder]


REPORTS: dict[str, ReportSpec] = {
    "latency": ReportSpec(
        code="PTR-LAT",
        title="API Latency & Cost Insight",
        template="latency_report.html",
        builder=LatencyReportBuilder,
    ),
    "throughput": ReportSpec(
        code="PTR-THR",
        title="Throughput & Capacity",
        template="throughput_report.html",
        builder=ThroughputReportBuilder,
    ),
    "resources": ReportSpec(
        code="PTR-RES",
        title="Resource Utilization Under Load",
        template="resource_utilization_report.html",
        builder=ResourceReportBuilder,
    ),
    "bottlenecks": ReportSpec(
        code="PTR-BNK",
        title="Bottleneck Analysis & Root-Cause",
        template="bottlenecks_report.html",
        builder=BottleneckReportBuilder,
    ),
}

VALID_REPORT_TYPES = frozenset(REPORTS)


def get_spec(report_type: str) -> ReportSpec:
    try:
        return REPORTS[report_type]
    except KeyError as exc:
        raise ValueError(f"invalid report_type: {report_type!r}") from exc
