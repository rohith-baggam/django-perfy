"""Pure server-side SVG chart helpers.

WeasyPrint cannot run JavaScript, so every chart in a report body is rendered
to an inline ``<svg>`` string here and dropped into the template (marked safe).
All functions are pure: same inputs -> same SVG, no DB access, no globals.

Geometry ported from the demo report generator:
  * ``gauge_svg``      — ring/progress gauges (Apdex, pool %, success rate)
  * ``donut_svg``      — segmented donut (error composition, severity mix)
  * ``area_svg``       — area + line trend (throughput, CPU/RAM)
  * ``bubble_svg``     — bubble quadrant (latency map, impact/effort matrix)
  * ``polyline_points``/``bar_width_pct`` — low-level primitives
"""

from __future__ import annotations

import math
from html import escape
from typing import Sequence

_TRACK: str = "#eaeef5"
_GRID: str = "#eef1f6"
_AXIS: str = "#cbd5e1"
_MUTED: str = "#94a3b8"
_LABEL: str = "#64748b"


def _f(value: float, ndigits: int = 1) -> str:
    """Format a float without a trailing ``.0`` where it reads cleaner."""
    return f"{round(float(value), ndigits):g}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------- #
# Primitives                                                                   #
# --------------------------------------------------------------------------- #
def polyline_points(
    values: Sequence[float],
    ymax: float,
    x0: float,
    x1: float,
    y_bottom: float,
    y_top: float,
) -> str:
    """Map ``values`` to an SVG points string across ``[x0,x1] x [y_bottom,y_top]``.

    ``ymax`` is the value mapped to ``y_top``; 0 maps to ``y_bottom``.
    """
    n: int = len(values)
    if n == 0:
        return ""
    ymax: float = ymax or 1.0
    if n == 1:
        x: float = (x0 + x1) / 2
        y: float = y_bottom - clamp(values[0] / ymax, 0, 1) * (y_bottom - y_top)
        return f"{_f(x)},{_f(y)}"
    span: float = x1 - x0
    pts: list[str] = []
    for i, value in enumerate(values):
        x = x0 + span * i / (n - 1)
        y = y_bottom - clamp((value or 0) / ymax, 0, 1) * (y_bottom - y_top)
        pts.append(f"{_f(x)},{_f(y)}")
    return " ".join(pts)


def _downsample(
    values: Sequence[float], xlabels: Sequence[str], max_points: int = 280
) -> tuple[list, list]:
    """Evenly thin a long series so big windows ('all', 30d) stay light.

    Keeps the visual shape (peaks survive because we step, not average) while
    bounding the SVG size — important for both preview weight and PDF render time.
    """
    n: int = len(values)
    if n <= max_points:
        return list(values), list(xlabels)
    step: float = n / max_points
    idx: list[int] = [int(i * step) for i in range(max_points)]
    idx[-1] = n - 1  # always keep the latest point
    vals: list[float] = [values[i] for i in idx]
    labs: list[str] = (
        [xlabels[i] for i in idx] if xlabels and len(xlabels) == n else list(xlabels)
    )
    return vals, labs


def bar_width_pct(value: float, vmax: float) -> float:
    """Percentage width for an in-cell data bar (0–100, clamped)."""
    if not vmax:
        return 0.0
    return round(clamp(value / vmax, 0, 1) * 100, 1)


# --------------------------------------------------------------------------- #
# Gauge (ring)                                                                 #
# --------------------------------------------------------------------------- #
def ring(pct: float, color: str, *, size: int = 120, stroke: int = 12) -> str:
    """A single progress ring (no centre text — the template overlays that)."""
    pct = clamp(float(pct or 0), 0, 100)
    radius: float = (size - stroke) / 2
    centre: float = size / 2
    circ: float = 2 * math.pi * radius
    arc: float = circ * pct / 100
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f'<circle cx="{_f(centre)}" cy="{_f(centre)}" r="{_f(radius)}" fill="none" '
        f'stroke="{_TRACK}" stroke-width="{stroke}"/>'
        f'<circle cx="{_f(centre)}" cy="{_f(centre)}" r="{_f(radius)}" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-dasharray="{_f(arc)} {_f(circ - arc)}" '
        f'transform="rotate(-90 {_f(centre)} {_f(centre)})"/>'
        f"</svg>"
    )


# Backwards-compatible alias matching the spec's helper name.
def gauge_svg(pct: float, color: str, *, size: int = 120, stroke: int = 12) -> str:
    return ring(pct, color, size=size, stroke=stroke)


# --------------------------------------------------------------------------- #
# Donut                                                                        #
# --------------------------------------------------------------------------- #
def donut(
    segments: Sequence[tuple[float, str]], *, size: int = 132, stroke: int = 20
) -> str:
    """Segmented donut. ``segments`` is a list of ``(value, color)`` pairs."""
    radius: float = (size - stroke) / 2
    centre: float = size / 2
    circ: float = 2 * math.pi * radius
    total: float = sum(max(0.0, float(v)) for v, _ in segments) or 1.0
    parts: list[str] = [
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f'<circle cx="{_f(centre)}" cy="{_f(centre)}" r="{_f(radius)}" fill="none" '
        f'stroke="{_TRACK}" stroke-width="{stroke}"/>'
    ]
    offset: float = 0.0
    for value, color in segments:
        frac: float = max(0.0, float(value)) / total
        arc: float = circ * frac
        parts.append(
            f'<circle cx="{_f(centre)}" cy="{_f(centre)}" r="{_f(radius)}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" '
            f'stroke-dasharray="{_f(arc)} {_f(circ - arc)}" '
            f'stroke-dashoffset="{_f(-offset)}" '
            f'transform="rotate(-90 {_f(centre)} {_f(centre)})"/>'
        )
        offset += arc
    parts.append("</svg>")
    return "".join(parts)


def donut_svg(segments: Sequence[tuple[float, str]], **kwargs) -> str:  # alias
    return donut(segments, **kwargs)


# --------------------------------------------------------------------------- #
# Area / line trend                                                            #
# --------------------------------------------------------------------------- #
def area_svg(
    values: Sequence[float],
    color: str,
    *,
    height: int = 230,
    width: int = 900,
    ymax: float | None = None,
    threshold: float | None = None,
    threshold_label: str = "",
    xlabels: Sequence[str] = (),
    fill_id: str = "areaFill",
) -> str:
    """Full area+line trend chart as an inline SVG string.

    Returns an empty-state SVG when there's no data so templates never special
    case it.
    """
    pad_l, pad_r, pad_t, pad_b = 70, 60, 24, 40
    x0, x1 = pad_l, width - pad_r
    y_top, y_bottom = pad_t, height - pad_b

    values, xlabels = _downsample(values, xlabels)

    if not values:
        return (
            f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'font-family="inherit"><text x="{width / 2}" y="{height / 2}" '
            f'text-anchor="middle" fill="{_MUTED}" font-size="13">'
            f"No data in this range</text></svg>"
        )

    vmax: float = ymax if ymax is not None else (max(values) * 1.15 or 1.0)
    vmax: float = vmax or 1.0
    pts: str = polyline_points(values, vmax, x0, x1, y_bottom, y_top)
    poly: str = f"{x0},{y_bottom} {pts} {x1},{y_bottom}"

    grid: str = "".join(
        f'<line x1="{x0}" y1="{_f(y)}" x2="{x1}" y2="{_f(y)}" stroke="{_GRID}"/>'
        for y in (y_top, (y_top + y_bottom) / 2, y_bottom)
    )
    yaxis: str = (
        f'<g fill="{_MUTED}" font-size="10" text-anchor="end">'
        f'<text x="{x0 - 8}" y="{y_top + 4}">{_f(vmax)}</text>'
        f'<text x="{x0 - 8}" y="{(y_top + y_bottom) / 2 + 4:g}">{_f(vmax / 2)}</text>'
        f'<text x="{x0 - 8}" y="{y_bottom}">0</text></g>'
    )
    thr: str = ""
    if threshold is not None and threshold <= vmax:
        ty: float = y_bottom - clamp(threshold / vmax, 0, 1) * (y_bottom - y_top)
        thr = (
            f'<line x1="{x0}" y1="{_f(ty)}" x2="{x1}" y2="{_f(ty)}" stroke="#d97706" '
            f'stroke-width="1" stroke-dasharray="5 4"/>'
            f'<text x="{x1}" y="{_f(ty - 4)}" text-anchor="end" font-size="10" '
            f'fill="#d97706">{escape(threshold_label)}</text>'
        )
    xax: str = ""
    if xlabels:
        step: int = max(1, len(xlabels) // 4)
        ticks: list[str] = []
        for i in range(0, len(xlabels), step):
            x: float = x0 + (x1 - x0) * (i / max(len(xlabels) - 1, 1))
            ticks.append(
                f'<text x="{_f(x)}" y="{height - 14}" text-anchor="middle">'
                f"{escape(str(xlabels[i]))}</text>"
            )
        xax = f'<g fill="{_MUTED}" font-size="10">{"".join(ticks)}</g>'

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'font-family="inherit">'
        f'<defs><linearGradient id="{fill_id}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity="0.30"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0.02"/></linearGradient></defs>'
        f"{grid}{yaxis}"
        f'<polygon points="{poly}" fill="url(#{fill_id})"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>'
        f"{thr}{xax}</svg>"
    )


# --------------------------------------------------------------------------- #
# Bubble quadrant                                                              #
# --------------------------------------------------------------------------- #
def _fmt_tick(value: float, suffix: str) -> str:
    text: str
    if value >= 1000:
        text: str = f"{value / 1000:.1f}k"
    elif value >= 100 or value == int(value):
        text: str = str(int(round(value)))
    else:
        text: str = f"{value:.1f}"
    return f"{text}{suffix}"


def bubble_svg(
    bubbles: Sequence[dict],
    *,
    width: int = 920,
    height: int = 380,
    xlabel: str = "",
    ylabel: str = "",
    x_max: float = 1.0,
    y_max: float = 1.0,
    x_suffix: str = "",
    y_suffix: str = "",
    threshold_frac: float | None = None,
    threshold_label: str = "",
    label_top: int = 6,
) -> str:
    """Scatter/bubble chart with real numeric axes, gridlines and tick values.

    Each bubble: ``{x, y, r, color, label}`` with x/y in [0,1] fractions of the
    plot area (0,0 = bottom-left). ``x_max``/``y_max`` are the data values at
    fraction 1, used to print axis tick values. To keep the plot legible only
    the ``label_top`` largest bubbles are labelled; the rest are plotted as
    points (full detail lives in the tables below the chart).
    """
    pad_l, pad_r, pad_t, pad_b = 92, 44, 30, 58
    x0, x1 = pad_l, width - pad_r
    y_top, y_bottom = pad_t, height - pad_b

    if not bubbles:
        return (
            f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'font-family="inherit"><text x="{width / 2}" y="{height / 2}" '
            f'text-anchor="middle" fill="{_MUTED}" font-size="13">'
            f"No data in this range</text></svg>"
        )

    fracs: list[float] = [0.0, 0.25, 0.5, 0.75, 1.0]
    # Gridlines + tick values on both axes.
    grid: list[str] = []
    xticks: list[str] = []
    yticks: list[str] = []
    for fr in fracs:
        gx: float = x0 + fr * (x1 - x0)
        gy: float = y_bottom - fr * (y_bottom - y_top)
        grid.append(
            f'<line x1="{_f(gx)}" y1="{y_top}" x2="{_f(gx)}" y2="{y_bottom}" stroke="{_GRID}"/>'
            f'<line x1="{x0}" y1="{_f(gy)}" x2="{x1}" y2="{_f(gy)}" stroke="{_GRID}"/>'
        )
        xticks.append(
            f'<text x="{_f(gx)}" y="{y_bottom + 16}" text-anchor="middle">'
            f"{_fmt_tick(fr * x_max, x_suffix)}</text>"
        )
        yticks.append(
            f'<text x="{x0 - 8}" y="{_f(gy + 3)}" text-anchor="end">'
            f"{_fmt_tick(fr * y_max, y_suffix)}</text>"
        )

    zone: str = ""
    thr: str = ""
    if threshold_frac is not None:
        ty: float = y_bottom - clamp(threshold_frac, 0, 1) * (y_bottom - y_top)
        zone = (
            f'<rect x="{x0}" y="{y_top}" width="{x1 - x0}" height="{_f(ty - y_top)}" '
            f'fill="#fee2e2" opacity="0.45"/>'
            f'<text x="{x1 - 8}" y="{y_top + 15}" text-anchor="end" font-size="10" '
            f'fill="#b91c1c" font-weight="700">FIX-FIRST ZONE</text>'
        )
        thr = (
            f'<line x1="{x0}" y1="{_f(ty)}" x2="{x1}" y2="{_f(ty)}" stroke="#b45309" '
            f'stroke-width="1.2" stroke-dasharray="5 4"/>'
            f'<text x="{x0 + 4}" y="{_f(ty - 4)}" font-size="10" fill="#b45309">'
            f"{escape(threshold_label)}</text>"
        )

    axes: str = (
        f'<line x1="{x0}" y1="{y_top}" x2="{x0}" y2="{y_bottom}" stroke="{_AXIS}" stroke-width="1.2"/>'
        f'<line x1="{x0}" y1="{y_bottom}" x2="{x1}" y2="{y_bottom}" stroke="{_AXIS}" stroke-width="1.2"/>'
        f'<g fill="{_MUTED}" font-size="9.5">{"".join(xticks)}{"".join(yticks)}</g>'
        f'<text x="26" y="{(y_top + y_bottom) / 2:g}" font-size="10.5" fill="{_LABEL}" '
        f'transform="rotate(-90 26 {(y_top + y_bottom) / 2:g})" text-anchor="middle">'
        f"{escape(ylabel)}</text>"
        f'<text x="{(x0 + x1) / 2:g}" y="{height - 8}" font-size="10.5" fill="{_LABEL}" '
        f'text-anchor="middle">{escape(xlabel)}</text>'
    )

    # Largest bubbles get a label; the rest stay as points to avoid pile-ups.
    order: list[int] = sorted(
        range(len(bubbles)), key=lambda i: float(bubbles[i].get("r", 8)), reverse=True
    )
    labelled: set[int] = set(order[:label_top])

    circles: list[str] = []
    labels: list[str] = []
    for i, b in enumerate(bubbles):
        cx: float = x0 + clamp(b.get("x", 0), 0, 1) * (x1 - x0)
        cy: float = y_bottom - clamp(b.get("y", 0), 0, 1) * (y_bottom - y_top)
        r: float = max(5.0, float(b.get("r", 8)))
        color: str = b.get("color", "#4f46e5")
        circles.append(
            f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{_f(r)}" fill="{color}" '
            f'fill-opacity="0.18" stroke="{color}" stroke-width="1.5"/>'
        )
        if i in labelled:
            lx: float = clamp(cx, x0 + 24, x1 - 24)
            ly: float = cy - r - 5
            if ly < y_top + 8:  # flip below if it would clip the top
                ly = cy + r + 12
            labels.append(
                f'<text x="{_f(lx)}" y="{_f(ly)}" text-anchor="middle" font-size="9.5" '
                f'font-weight="700" fill="{color}" paint-order="stroke" '
                f'stroke="#ffffff" stroke-width="2.6" stroke-linejoin="round">'
                f'{escape(str(b.get("label", "")))}</text>'
            )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height - 24}" '
        f'font-family="inherit">{"".join(grid)}{zone}{thr}{axes}'
        f'{"".join(circles)}{"".join(labels)}</svg>'
    )
