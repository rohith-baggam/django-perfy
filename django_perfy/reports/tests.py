"""Unit tests for the performance report export feature.

Covers: the range resolver, the latency builder's numeric output (incl. Apdex
math) on a fixed fixture, and a PDF-bytes smoke test. Run with:

    python manage.py test django_perfy.reports
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from django_perfy.models import APIRequestLog, PerformanceSummary

from .builders import LatencyReportBuilder
from .ranges import VALID_RANGES, resolve_range, summary_granularity
from .renderer import render_report_pdf


class PerfReportTestCase(TestCase):
    """Base case that permits every alias.

    Performance models may live on a secondary database (via the bundled
    router), while auth/session tables stay on ``default`` — so these tests
    touch more than one alias.
    """

    databases: str = "__all__"


class RangeResolverTests(PerfReportTestCase):
    def test_all_keys_resolve(self):
        for key in VALID_RANGES:
            start, end = resolve_range(key)
            self.assertIsNotNone(end)
            if key == "all":
                self.assertIsNone(start)
            else:
                self.assertIsNotNone(start)
                self.assertLess(start, end)

    def test_invalid_range_raises(self):
        with self.assertRaises(ValueError):
            resolve_range("bogus")

    def test_granularity_buckets(self):
        self.assertEqual(summary_granularity("1h"), "minute")
        self.assertEqual(summary_granularity("6h"), "minute")
        self.assertEqual(summary_granularity("24h"), "hour")
        self.assertEqual(summary_granularity("all"), "hour")


class LatencyBuilderTests(PerfReportTestCase):
    """Apdex and weighted within-SLA on a controlled fixture.

    All rows are fast (< 500 ms) and 2xx, so every row is sampled at the same
    inverse-probability weight — making the expected Apdex exact:
      7 satisfied (<=300 ms) + 3 tolerating (300<rt<=1200) =>
      Apdex = (7 + 3/2) / 10 = 0.85
    within-SLA (< 300 ms) = 7 / 10 = 70%.
    """

    ENDPOINT = "/api/v1/messages/"

    def setUp(self):
        for _ in range(7):
            APIRequestLog.objects.create(
                endpoint=self.ENDPOINT,
                method="GET",
                status_code=200,
                response_time_ms=100,
                db_query_count=2,
                db_time_ms=20,
                response_size_bytes=1000,
                concurrent_requests=3,
            )
        for _ in range(3):
            APIRequestLog.objects.create(
                endpoint=self.ENDPOINT,
                method="GET",
                status_code=200,
                response_time_ms=400,
                db_query_count=4,
                db_time_ms=80,
                response_size_bytes=1000,
                concurrent_requests=3,
            )
        PerformanceSummary.objects.create(
            log_type="api",
            endpoint_or_consumer=self.ENDPOINT,
            granularity="hour",
            window_start=timezone.now(),
            total_requests=100,
            avg_response_time_ms=160,
            p50_ms=100,
            p95_ms=400,
            p99_ms=450,
            error_count=0,
        )

    def test_apdex_and_sla(self):
        start, end = resolve_range("24h")
        ctx = LatencyReportBuilder(start, end, range_key="24h").build()
        self.assertTrue(ctx["has_data"])
        self.assertAlmostEqual(ctx["apdex"], 0.85, places=2)

        row = next(r for r in ctx["rows"] if r["endpoint"] == self.ENDPOINT)
        self.assertEqual(row["within_sla"], 70.0)
        self.assertEqual(row["p95"], 400)
        self.assertEqual(row["tail_spread"], round(450 / 100, 1))

    def test_apdex_t_is_configurable(self):
        start, end = resolve_range("24h")
        # With T=500, all 10 rows are "satisfied" -> Apdex 1.0.
        ctx = LatencyReportBuilder(start, end, range_key="24h", apdex_t_ms=500).build()
        self.assertAlmostEqual(ctx["apdex"], 1.0, places=2)


class EmptyRangeTests(PerfReportTestCase):
    def test_empty_range_is_graceful(self):
        start, end = resolve_range("1h")
        ctx = LatencyReportBuilder(start, end, range_key="1h").build()
        self.assertFalse(ctx["has_data"])


class PdfSmokeTests(PerfReportTestCase):
    def test_pdf_bytes(self):
        # Renders even with no data (graceful empty report) -> valid PDF.
        pdf = render_report_pdf("bottlenecks", *resolve_range("24h"), range_key="24h")
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)


class ReportEndpointTests(PerfReportTestCase):
    def setUp(self):
        self.client = Client()
        user = get_user_model().objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        self.client.force_login(user)

    def _post(self, path, body):
        return self.client.post(
            f"/dashboard/reports/{path}", body, content_type="application/json"
        )

    def test_preview_returns_html(self):
        res = self._post("preview/", {"report_type": "latency", "range": "24h"})
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"<html", res.content)

    def test_download_returns_pdf(self):
        res = self._post("download/", {"report_type": "resources", "range": "24h"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertIn("attachment", res["Content-Disposition"])

    def test_invalid_report_type_rejected(self):
        res = self._post("preview/", {"report_type": "nope", "range": "24h"})
        self.assertEqual(res.status_code, 400)

    def test_invalid_email_rejected(self):
        res = self._post(
            "email/", {"report_type": "latency", "range": "24h", "email": "bad"}
        )
        self.assertEqual(res.status_code, 400)
