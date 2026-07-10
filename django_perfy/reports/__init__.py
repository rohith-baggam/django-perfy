"""Performance report export — preview, PDF download and email.

This package builds the four downloadable performance reports (latency,
throughput, resource utilisation, bottleneck analysis) from the same
sampling-corrected telemetry the dashboard uses. Nothing here mutates the
running dashboard's behaviour — the builders only *read* via the existing
``dashboard.views`` helpers.
"""
