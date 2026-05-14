"""
charts.py — shared chart renderers for the digital-twin skill.

Two backends:
  * ASCII (terminal-friendly, used in PROFILE.md)
  * Inline SVG (self-contained, used in PROFILE.html — no external assets)

All functions are pure: data in, string out. No I/O. Importable from
synthesize.py via `from references.visualization import charts as ch`.
"""
from __future__ import annotations

import html
import math
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Palette (used for SVG only; ASCII is monochrome)
# ---------------------------------------------------------------------------

PAL = {
    "fg": "#1f2937",        # slate-800
    "muted": "#6b7280",     # gray-500
    "grid": "#e5e7eb",      # gray-200
    "approval": "#10b981",  # emerald-500
    "explicit": "#ef4444",  # red-500
    "implicit": "#f59e0b",  # amber-500
    "neutral": "#9ca3af",   # gray-400
    "primary": "#3b82f6",   # blue-500
    "early": "#94a3b8",     # slate-400
    "late": "#0ea5e9",      # sky-500
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bar(width: int, max_width: int, char: str = "█") -> str:
    return char * max(0, min(width, max_width))


def _scale(val: float, vmax: float, width: int) -> int:
    if vmax <= 0:
        return 0
    return int(round(width * val / vmax))


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _svg_open(width: int, height: int, title: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="{_esc(title)}" '
        f'style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; '
        f'font-size: 12px; color: {PAL["fg"]};">'
    )


def _svg_close() -> str:
    return "</svg>"


# ---------------------------------------------------------------------------
# Hour-of-day heatmap (24 cells)
# ---------------------------------------------------------------------------


def hour_heatmap_ascii(by_hour: list[int] | None) -> str:
    if not by_hour or len(by_hour) < 24:
        return "_no hour data_"
    vmax = max(by_hour) or 1
    rows = []
    rows.append("hour: " + " ".join(f"{h:>3d}" for h in range(24)))
    rows.append("freq: " + " ".join(f"{v:>3d}" for v in by_hour))
    # Bar row: each hour gets a vertical-density char proxy.
    chars = " ▁▂▃▄▅▆▇█"
    bar_row = []
    for v in by_hour:
        idx = int(round((v / vmax) * (len(chars) - 1)))
        bar_row.append(chars[idx] * 3)
    rows.append("bars: " + " ".join(bar_row))
    return "```\n" + "\n".join(rows) + "\n```"


def hour_heatmap_svg(by_hour: list[int] | None, peak_hour: int | None = None) -> str:
    """24-hour activity as a vertical bar chart (clearer than a heatmap).

    Peak hour gets a deeper saturation + a small "peak" tag above the bar.
    Working hours (8-18) get a subtle background band so off-hours stand out.
    Y-axis shows max value as a reference; baseline grid at 25/50/75/100%.
    """
    if not by_hour or len(by_hour) < 24:
        return '<p><em>no hour data</em></p>'
    vmax = max(by_hour) or 1

    bar_w, gap = 22, 6
    pad_left, pad_right, pad_top, pad_bottom = 44, 16, 36, 32
    chart_h = 180
    width = pad_left + 24 * (bar_w + gap) - gap + pad_right
    height = pad_top + chart_h + pad_bottom

    out = [_svg_open(width, height, "Hour of day activity")]

    # Working-hours band (8-18) for context — very subtle
    band_x_start = pad_left + 8 * (bar_w + gap) - gap / 2
    band_x_end = pad_left + 19 * (bar_w + gap) - gap / 2 - gap
    band_w = band_x_end - band_x_start
    out.append(
        f'<rect x="{band_x_start}" y="{pad_top}" width="{band_w}" '
        f'height="{chart_h}" fill="#f1f5f9" opacity="0.6"/>'
    )

    # Y-axis gridlines at 0, 25, 50, 75, 100 % of max
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = pad_top + chart_h - int(chart_h * frac)
        dash_attr = "" if frac in (0.0, 1.0) else ' stroke-dasharray="2,3"'
        out.append(
            f'<line x1="{pad_left - 6}" y1="{y}" x2="{width - pad_right}" '
            f'y2="{y}" stroke="{PAL["grid"]}" stroke-width="1"{dash_attr}/>'
        )
    # Y-axis label (max)
    out.append(
        f'<text x="{pad_left - 10}" y="{pad_top + 4}" text-anchor="end" '
        f'fill="{PAL["muted"]}" font-size="10">{vmax:,}</text>'
    )
    out.append(
        f'<text x="{pad_left - 10}" y="{pad_top + chart_h + 4}" text-anchor="end" '
        f'fill="{PAL["muted"]}" font-size="10">0</text>'
    )

    # Bars
    for h, v in enumerate(by_hour):
        bar_h = max(2, int(round((v / vmax) * chart_h))) if v > 0 else 0
        x = pad_left + h * (bar_w + gap)
        y = pad_top + chart_h - bar_h
        is_peak = peak_hour is not None and h == peak_hour
        fill = PAL["explicit"] if is_peak else PAL["primary"]
        out.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" '
            f'fill="{fill}" rx="2"/>'
        )
        # Peak tag above the bar
        if is_peak and bar_h > 0:
            out.append(
                f'<text x="{x + bar_w / 2}" y="{y - 6}" text-anchor="middle" '
                f'fill="{PAL["explicit"]}" font-size="10" font-weight="600">'
                f'peak ({v:,})</text>'
            )
        # Hour label
        out.append(
            f'<text x="{x + bar_w / 2}" y="{pad_top + chart_h + 14}" '
            f'text-anchor="middle" fill="{PAL["muted"]}" font-size="10">'
            f'{h:02d}</text>'
        )

    # Footer hint
    out.append(
        f'<text x="{pad_left}" y="{height - 4}" fill="{PAL["muted"]}" font-size="10" '
        f'font-style="italic">shaded band: typical working hours (08–18 local)</text>'
    )

    out.append(_svg_close())
    return "".join(out)


# ---------------------------------------------------------------------------
# Day-of-week histogram
# ---------------------------------------------------------------------------


def day_histogram_ascii(by_day: dict | list | None) -> str:
    if not by_day:
        return "_no day data_"
    # Accept dict {Mon: n} or list of 7 ints
    if isinstance(by_day, dict):
        vals = [by_day.get(d, 0) for d in DAY_NAMES]
    else:
        vals = list(by_day)[:7]
    vmax = max(vals) or 1
    lines = []
    for name, v in zip(DAY_NAMES, vals):
        bar = _bar(_scale(v, vmax, 30), 30)
        lines.append(f"{name} {bar:<30} {v}")
    return "```\n" + "\n".join(lines) + "\n```"


def day_histogram_svg(by_day: dict | list | None, peak_day: str | None = None) -> str:
    if not by_day:
        return '<p><em>no day data</em></p>'
    if isinstance(by_day, dict):
        vals = [by_day.get(d, 0) for d in DAY_NAMES]
    else:
        vals = list(by_day)[:7]
    vmax = max(vals) or 1
    total = sum(vals) or 1
    bar_w, gap = 64, 22
    pad_left, pad_right, pad_top, pad_bottom = 36, 16, 16, 44
    chart_h = 170
    width = pad_left + 7 * (bar_w + gap) - gap + pad_right
    height = pad_top + chart_h + pad_bottom
    out = [_svg_open(width, height, "Day of week histogram")]

    # Light gridlines at 25/50/75/100% of max
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = pad_top + chart_h - int(chart_h * frac)
        out.append(
            f'<line x1="{pad_left}" y1="{y}" x2="{width - pad_right}" y2="{y}" '
            f'stroke="{PAL["grid"]}" stroke-dasharray="2,3" stroke-width="1"/>'
        )
    # Baseline
    out.append(
        f'<line x1="{pad_left}" y1="{pad_top + chart_h}" x2="{width - pad_right}" '
        f'y2="{pad_top + chart_h}" stroke="{PAL["grid"]}" stroke-width="1"/>'
    )

    for i, (name, v) in enumerate(zip(DAY_NAMES, vals)):
        h = max(2, int(round((v / vmax) * chart_h))) if v > 0 else 0
        x = pad_left + i * (bar_w + gap)
        y = pad_top + chart_h - h
        is_peak = name == peak_day
        fill = PAL["explicit"] if is_peak else PAL["primary"]
        share = round(100 * v / total, 1)
        out.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{h}" '
            f'fill="{fill}" rx="3"/>'
        )
        # Value (count) above the bar
        out.append(
            f'<text x="{x + bar_w / 2}" y="{y - 14}" text-anchor="middle" '
            f'fill="{PAL["fg"]}" font-size="12" font-weight="600">{v:,}</text>'
        )
        # Share % below count
        out.append(
            f'<text x="{x + bar_w / 2}" y="{y - 2}" text-anchor="middle" '
            f'fill="{PAL["muted"]}" font-size="10">{share}%</text>'
        )
        # Day label
        weight = "600" if is_peak else "400"
        text_fill = PAL["explicit"] if is_peak else PAL["fg"]
        out.append(
            f'<text x="{x + bar_w / 2}" y="{pad_top + chart_h + 18}" '
            f'text-anchor="middle" fill="{text_fill}" font-size="12" '
            f'font-weight="{weight}">{name}</text>'
        )
        # "peak" tag below the peak day
        if is_peak:
            out.append(
                f'<text x="{x + bar_w / 2}" y="{pad_top + chart_h + 32}" '
                f'text-anchor="middle" fill="{PAL["explicit"]}" font-size="10" '
                f'font-style="italic">peak day</text>'
            )

    out.append(_svg_close())
    return "".join(out)


# ---------------------------------------------------------------------------
# Convergence donut (approval/explicit/implicit/neutral)
# ---------------------------------------------------------------------------


def convergence_donut_svg(counts: dict) -> str:
    if not counts:
        return '<p><em>no convergence data</em></p>'
    order = [
        ("approval", PAL["approval"], "Approval"),
        ("neutral", PAL["neutral"], "Neutral"),
        ("implicit_pushback", PAL["implicit"], "Implicit pushback"),
        ("explicit_pushback", PAL["explicit"], "Explicit pushback"),
    ]
    total = sum(counts.get(k, 0) for k, _, _ in order)
    if total <= 0:
        return '<p><em>no convergence data</em></p>'

    cx, cy, r_outer, r_inner = 150, 160, 120, 76
    width, height = 540, 340
    out = [_svg_open(width, height, "Reply classification donut")]
    out.append(
        f'<text x="20" y="22" font-size="14" font-weight="600" fill="{PAL["fg"]}">'
        f'Reply classification</text>'
    )
    out.append(
        f'<text x="20" y="40" font-size="11" fill="{PAL["muted"]}">'
        f'{total:,} (assistant turn → user reply) pairs</text>'
    )
    start = -math.pi / 2
    for k, color, _label in order:
        v = counts.get(k, 0)
        if v <= 0:
            continue
        frac = v / total
        end = start + frac * 2 * math.pi
        large_arc = 1 if frac > 0.5 else 0
        x1 = cx + r_outer * math.cos(start)
        y1 = cy + r_outer * math.sin(start)
        x2 = cx + r_outer * math.cos(end)
        y2 = cy + r_outer * math.sin(end)
        x3 = cx + r_inner * math.cos(end)
        y3 = cy + r_inner * math.sin(end)
        x4 = cx + r_inner * math.cos(start)
        y4 = cy + r_inner * math.sin(start)
        path = (
            f"M {x1:.2f} {y1:.2f} "
            f"A {r_outer} {r_outer} 0 {large_arc} 1 {x2:.2f} {y2:.2f} "
            f"L {x3:.2f} {y3:.2f} "
            f"A {r_inner} {r_inner} 0 {large_arc} 0 {x4:.2f} {y4:.2f} "
            "Z"
        )
        out.append(
            f'<path d="{path}" fill="{color}" stroke="white" stroke-width="2"/>'
        )
        # In-segment % label if slice is large enough
        if frac > 0.08:
            mid = (start + end) / 2
            r_label = (r_outer + r_inner) / 2
            tx = cx + r_label * math.cos(mid)
            ty = cy + r_label * math.sin(mid)
            pct = round(100 * frac, 1)
            out.append(
                f'<text x="{tx}" y="{ty + 4}" text-anchor="middle" fill="white" '
                f'font-size="13" font-weight="700">{pct}%</text>'
            )
        start = end

    # center label
    out.append(
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="26" '
        f'font-weight="700" fill="{PAL["fg"]}">{total:,}</text>'
    )
    out.append(
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" fill="{PAL["muted"]}" '
        f'font-size="12">pairs</text>'
    )

    # Legend — bigger, with bold counts
    lx, ly = 310, 80
    for i, (k, color, label) in enumerate(order):
        v = counts.get(k, 0)
        pct = round(100 * v / total, 1) if total else 0
        y = ly + i * 48
        out.append(
            f'<rect x="{lx}" y="{y}" width="20" height="20" fill="{color}" rx="4"/>'
        )
        out.append(
            f'<text x="{lx + 30}" y="{y + 15}" fill="{PAL["fg"]}" font-size="13" '
            f'font-weight="600">{label}</text>'
        )
        out.append(
            f'<text x="{lx + 30}" y="{y + 33}" fill="{PAL["muted"]}" font-size="12">'
            f'<tspan font-weight="600" fill="{PAL["fg"]}">{v:,}</tspan> · {pct}%</text>'
        )

    out.append(_svg_close())
    return "".join(out)


def convergence_bars_ascii(counts: dict) -> str:
    if not counts:
        return "_no convergence data_"
    order = ["approval", "neutral", "implicit_pushback", "explicit_pushback"]
    vmax = max(counts.get(k, 0) for k in order) or 1
    lines = []
    for k in order:
        v = counts.get(k, 0)
        bar = _bar(_scale(v, vmax, 30), 30)
        lines.append(f"{k:>18} {bar:<30} {v:,}")
    return "```\n" + "\n".join(lines) + "\n```"


# ---------------------------------------------------------------------------
# Word-frequency horizontal bars (top approval / pushback words)
# ---------------------------------------------------------------------------


def word_bars_ascii(pairs: Sequence[Sequence], limit: int = 10) -> str:
    if not pairs:
        return "_no data_"
    items = list(pairs)[:limit]
    vmax = max(v for _, v in items) or 1
    lines = []
    for w, v in items:
        bar = _bar(_scale(v, vmax, 30), 30)
        lines.append(f"{str(w)[:14]:>14} {bar:<30} {v:,}")
    return "```\n" + "\n".join(lines) + "\n```"


def word_bars_svg(
    pairs: Sequence[Sequence],
    limit: int = 10,
    color: str = PAL["primary"],
    title: str = "Top words",
) -> str:
    if not pairs:
        return '<p><em>no data</em></p>'
    items = list(pairs)[:limit]
    vmax = max(v for _, v in items) or 1
    row_h = 26
    pad_left, pad_top = 120, 30
    bar_max = 320
    width = pad_left + bar_max + 80
    height = pad_top + row_h * len(items) + 16
    out = [_svg_open(width, height, title)]
    out.append(
        f'<text x="10" y="20" font-size="13" font-weight="600" fill="{PAL["fg"]}">{_esc(title)}</text>'
    )
    for i, (w, v) in enumerate(items):
        y = pad_top + i * row_h
        bw = int(round((v / vmax) * bar_max))
        out.append(
            f'<text x="{pad_left - 8}" y="{y + 14}" text-anchor="end" '
            f'fill="{PAL["fg"]}">{_esc(w)}</text>'
        )
        out.append(
            f'<rect x="{pad_left}" y="{y + 2}" width="{bw}" height="{row_h - 8}" '
            f'fill="{color}" rx="2"/>'
        )
        out.append(
            f'<text x="{pad_left + bw + 6}" y="{y + 14}" fill="{PAL["muted"]}">{v:,}</text>'
        )
    out.append(_svg_close())
    return "".join(out)


# ---------------------------------------------------------------------------
# OOS / AC drift comparison (early vs late half of plans)
# ---------------------------------------------------------------------------


def drift_chart_ascii(drift: dict | None) -> str:
    if not drift:
        return "_no drift data (need ≥4 plans)_"
    rows = [
        ("OOS adoption",
         f"{drift.get('early_oos_pct', 0)}%",
         f"{drift.get('late_oos_pct', 0)}%"),
        ("Avg AC count",
         f"{drift.get('early_ac_avg', 0)}",
         f"{drift.get('late_ac_avg', 0)}"),
    ]
    lines = ["| Metric | Early | Late |", "| --- | ---: | ---: |"]
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} |")
    return "\n".join(lines)


def drift_chart_svg(drift: dict | None) -> str:
    if not drift:
        return '<p><em>no drift data (need ≥4 plans)</em></p>'
    metrics = [
        ("Out-of-scope adoption (%)",
         float(drift.get("early_oos_pct", 0)),
         float(drift.get("late_oos_pct", 0)),
         "%"),
        ("Avg acceptance criteria",
         float(drift.get("early_ac_avg", 0)),
         float(drift.get("late_ac_avg", 0)),
         ""),
    ]
    pad_left, pad_top = 200, 36
    bar_max = 280
    row_h = 80
    width = pad_left + bar_max + 80
    height = pad_top + row_h * len(metrics) + 16
    out = [_svg_open(width, height, "Drift early vs late")]
    out.append(
        f'<text x="10" y="20" font-size="13" font-weight="600" fill="{PAL["fg"]}">'
        f'Drift: early half vs late half of plans</text>'
    )
    for i, (label, early, late, unit) in enumerate(metrics):
        ybase = pad_top + i * row_h
        vmax = max(early, late) or 1
        bw_e = int(round((early / vmax) * bar_max))
        bw_l = int(round((late / vmax) * bar_max))
        out.append(
            f'<text x="{pad_left - 8}" y="{ybase + 14}" text-anchor="end" '
            f'fill="{PAL["fg"]}">{label}</text>'
        )
        # early
        out.append(
            f'<rect x="{pad_left}" y="{ybase + 2}" width="{bw_e}" height="22" '
            f'fill="{PAL["early"]}" rx="2"/>'
        )
        out.append(
            f'<text x="{pad_left + bw_e + 6}" y="{ybase + 18}" fill="{PAL["muted"]}">'
            f'early: {early:g}{unit}</text>'
        )
        # late
        out.append(
            f'<rect x="{pad_left}" y="{ybase + 32}" width="{bw_l}" height="22" '
            f'fill="{PAL["late"]}" rx="2"/>'
        )
        out.append(
            f'<text x="{pad_left + bw_l + 6}" y="{ybase + 48}" fill="{PAL["muted"]}">'
            f'late: {late:g}{unit}</text>'
        )
    out.append(_svg_close())
    return "".join(out)


# ---------------------------------------------------------------------------
# Prompt-length distribution sparkline (median, p90, max)
# ---------------------------------------------------------------------------


def percentile_bar_svg(median: float, p90: float, vmax_hint: float | None = None) -> str:
    median = float(median or 0)
    p90 = float(p90 or 0)
    vmax = max(p90 * 1.2, vmax_hint or 0, 1)
    width, height = 480, 80
    pad = 20
    bar_w = width - 2 * pad
    out = [_svg_open(width, height, "Prompt length distribution")]
    out.append(
        f'<text x="{pad}" y="18" font-size="13" font-weight="600" fill="{PAL["fg"]}">'
        f'Prompt length (chars)</text>'
    )
    y = 38
    out.append(
        f'<rect x="{pad}" y="{y}" width="{bar_w}" height="14" fill="{PAL["grid"]}" rx="2"/>'
    )
    # Median tick
    mx = pad + int(round((median / vmax) * bar_w))
    out.append(
        f'<line x1="{mx}" y1="{y - 6}" x2="{mx}" y2="{y + 20}" '
        f'stroke="{PAL["primary"]}" stroke-width="2"/>'
    )
    out.append(
        f'<text x="{mx}" y="{y + 36}" text-anchor="middle" fill="{PAL["primary"]}">'
        f'median {median:.0f}</text>'
    )
    # p90 tick
    px = pad + int(round((p90 / vmax) * bar_w))
    out.append(
        f'<line x1="{px}" y1="{y - 6}" x2="{px}" y2="{y + 20}" '
        f'stroke="{PAL["explicit"]}" stroke-width="2"/>'
    )
    out.append(
        f'<text x="{px}" y="{y + 36}" text-anchor="middle" fill="{PAL["explicit"]}">'
        f'p90 {p90:.0f}</text>'
    )
    out.append(_svg_close())
    return "".join(out)

