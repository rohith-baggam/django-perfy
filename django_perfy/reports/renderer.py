"""Thin rendering layer used by both preview and PDF.

A self-contained Jinja2 ``Environment`` (FileSystemLoader over this package's
``templates/`` dir) keeps report rendering fully decoupled from the live
dashboard's Django template configuration — nothing in ``settings.TEMPLATES``
needs to change.
"""

from __future__ import annotations

import functools
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .ranges import resolve_range
from .registry import get_spec

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _format_number(value: object) -> str:
    """Human-readable counts: 1.2k, 3.4M — mirrors the dashboard filter."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(round(number))


@functools.lru_cache(maxsize=1)
def get_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["format_number"] = _format_number
    return env


def render_report_html(
    report_type: str,
    start: datetime | None,
    end: datetime,
    *,
    range_key: str | None = None,
) -> str:
    """Select spec, run its builder, render the template to an HTML string."""
    spec = get_spec(report_type)
    context = spec.builder(start, end, range_key=range_key).build()
    template = get_environment().get_template(spec.template)
    return template.render(**context)


def render_report_pdf(
    report_type: str,
    start: datetime | None,
    end: datetime,
    *,
    range_key: str | None = None,
) -> bytes:
    """Render to HTML then to PDF bytes via WeasyPrint."""
    # Imported lazily so importing this module never hard-requires WeasyPrint's
    # native libs (keeps preview working even if PDF deps are unavailable).
    from weasyprint import HTML

    html = render_report_html(report_type, start, end, range_key=range_key)
    return HTML(string=html, base_url=_TEMPLATE_DIR).write_pdf()


def render_for_range(report_type: str, range_key: str) -> str:
    start, end = resolve_range(range_key)
    return render_report_html(report_type, start, end, range_key=range_key)
