"""Report endpoints — preview (HTML), download (PDF), email (async).

Views are thin: they validate input and delegate all business logic to the
builders/renderer. They follow the same staff-only, class-based pattern as
``django_perfy.views.CorrelationView``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from django.contrib.admin.views.decorators import staff_member_required

from .ranges import VALID_RANGES, resolve_range
from .registry import VALID_REPORT_TYPES
from .renderer import render_report_html, render_report_pdf

logger = logging.getLogger(__name__)


@method_decorator(staff_member_required, name="dispatch")
class BaseReportView(View):
    """Shared JSON parsing + allow-list validation for report endpoints."""

    require_email = False

    def parse(self, request) -> tuple[dict[str, Any] | None, JsonResponse | None]:
        try:
            payload = json.loads(request.body or b"{}")
        except (ValueError, TypeError):
            return None, JsonResponse({"error": "invalid JSON body"}, status=400)

        report_type = str(payload.get("report_type", "")).strip()
        range_key = str(payload.get("range", "")).strip()

        if report_type not in VALID_REPORT_TYPES:
            return None, JsonResponse({"error": "invalid report_type"}, status=400)
        if range_key not in VALID_RANGES:
            return None, JsonResponse({"error": "invalid range"}, status=400)

        data: dict[str, Any] = {"report_type": report_type, "range": range_key}

        if self.require_email:
            email = str(payload.get("email", "")).strip()
            try:
                validate_email(email)
            except ValidationError:
                return None, JsonResponse({"error": "invalid email"}, status=400)
            data["email"] = email

        return data, None


class ReportPreviewView(BaseReportView):
    """POST -> rendered report HTML (string) for the modal's iframe srcdoc."""

    def post(self, request):
        data, error = self.parse(request)
        if error:
            return error
        try:
            start, end = resolve_range(data["range"])
            html = render_report_html(
                data["report_type"], start, end, range_key=data["range"]
            )
        except Exception:
            logger.exception("report preview failed")
            return JsonResponse({"error": "failed to render report"}, status=500)
        return HttpResponse(html, content_type="text/html; charset=utf-8")


class ReportDownloadView(BaseReportView):
    """POST -> the previewed report as a PDF attachment."""

    def post(self, request):
        from .registry import get_spec

        data, error = self.parse(request)
        if error:
            return error
        try:
            start, end = resolve_range(data["range"])
            pdf = render_report_pdf(
                data["report_type"], start, end, range_key=data["range"]
            )
        except Exception:
            logger.exception("report PDF generation failed")
            return JsonResponse({"error": "failed to generate PDF"}, status=500)

        document_id = (
            get_spec(data["report_type"])
            .builder(start, end, range_key=data["range"])
            .document_id
        )
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{document_id}.pdf"'
        return response


class ReportEmailView(BaseReportView):
    """POST -> enqueue async email task, return 202 immediately."""

    require_email = True

    def post(self, request):
        data, error = self.parse(request)
        if error:
            return error
        # Imported here so a missing broker at import time can't break preview.
        from django_perfy.tasks import send_report_email

        try:
            send_report_email.delay(data["report_type"], data["range"], data["email"])
        except Exception:
            logger.exception("failed to enqueue report email")
            return JsonResponse({"error": "failed to enqueue email"}, status=500)
        return JsonResponse(
            {
                "status": "queued",
                "message": f"Report will be emailed to {data['email']} shortly.",
            },
            status=202,
        )
