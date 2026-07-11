from __future__ import annotations

import os

from jinja2 import Environment

from django.templatetags.static import static
from django.urls import reverse

_STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static",
    "performance",
    "dashboard",
)


def _asset_version() -> str:
    """Cache-busting token derived from the dashboard asset mtimes.

    Appended as ``?v=`` to the JS/CSS URLs so browsers and proxies fetch the
    current build instead of a stale cached copy (filenames are unhashed).
    """
    latest: float = 0.0
    for name in ("dashboard.js", "dashboard.css"):
        try:
            latest: float = max(
                latest, os.path.getmtime(os.path.join(_STATIC_DIR, name))
            )
        except OSError:
            pass
    return str(int(latest))


def _format_number(value: object) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"

    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(round(number))


def make_environment(**options: object) -> Environment:
    env = Environment(**options)
    env.globals.update(
        {
            "static": static,
            "url": reverse,
            "asset_version": _asset_version(),
        }
    )
    env.filters["format_number"] = _format_number
    return env
