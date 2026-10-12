"""Custom chart widgets.

Flet 1.0 removed the native PieChart/BarChart/LineChart controls, so these are
hand-built from primitives:

* DonutChart -> a Canvas of Arc slices with a hole and a legend.
* BarChart   -> responsive Container bars (rounded tops) on a shared baseline.

Both are pure functions of data -> Control, so the data layer stays independent.
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft
from flet.canvas import Arc, Canvas, Circle
from flet.controls.painting import Paint, PaintingStyle

from utils import money, money_short


@dataclass(frozen=True)
class Slice:
    """One labelled segment of a donut chart."""

    label: str
    value: float
    color: str  # hex string


def DonutChart(
    slices: list[Slice],
    *,
    size: int = 180,
    hole_ratio: float = 0.62,
    center_title: str = "",
    center_value: str = "",
    empty_hint: str = "No data",
) -> ft.Control:
    """Render a donut with a centred total and a colour legend beneath.

    Falls back to a friendly placeholder when there is nothing to plot.
    """
    total = sum(s.value for s in slices)
    legend = _legend(slices, total)

    if total <= 0 or not slices:
        donut = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.PIE_CHART_OUTLINE, size=40, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(empty_hint, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            width=size,
            height=size,
            alignment=ft.Alignment.CENTER,
        )
        return ft.Column([donut], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16)

    # Build arc slices starting from the top (12 o'clock = -90 degrees).
    cx = size / 2
    hole = size * hole_ratio / 2
    shapes: list = []
    angle = -90.0
    for s in slices:
        sweep = 360.0 * s.value / total
        # A hairline gap keeps adjacent same-ish colours readable.
        gap = 1.2 if sweep > 8 else 0.0
        shapes.append(
            Arc(
                x=0, y=0, width=size, height=size,
                start_angle=angle + gap / 2,
                sweep_angle=max(sweep - gap, 0.5),
                use_center=True,
                paint=Paint(color=s.color, style=PaintingStyle.FILL),
            )
        )
        angle += sweep

    # Punch the hole with the caller-provided background colour.
    shapes.append(
        Circle(x=cx, y=cx, radius=hole, paint=Paint(color=ft.Colors.SURFACE_CONTAINER_LOW, style=PaintingStyle.FILL))
    )

    canvas = Canvas(shapes=shapes, width=size, height=size)

    center = ft.Container(
        content=ft.Column(
            [
                ft.Text(center_value, size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                ft.Text(center_title, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        ),
        width=size,
        height=size,
        alignment=ft.Alignment.CENTER,
    )

    donut = ft.Stack(
        width=size,
        height=size,
        controls=[canvas, center],
    )

    return ft.Column(
        [donut, legend],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=16,
    )


def _legend(slices: list[Slice], total: float) -> ft.Control:
    """Colour chips with label, amount and percentage for each slice."""
    rows: list[ft.Control] = []
    for s in slices:
        pct = (s.value / total * 100) if total else 0
        rows.append(
            ft.Row(
                [
                    ft.Container(width=12, height=12, border_radius=3, bgcolor=s.color),
                    ft.Text(s.label, size=13, color=ft.Colors.ON_SURFACE, expand=True,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"{money(s.value)}  \u00b7  {pct:.0f}%", size=13,
                            color=ft.Colors.ON_SURFACE_VARIANT),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            )
        )
    return ft.Container(
        content=ft.Column(rows, spacing=8),
        width=320,
    )


@dataclass(frozen=True)
class Bar:
    """One bar of a bar chart."""

    label: str        # axis caption (e.g. "M", "12")
    value: float
    highlight: bool = False  # e.g. "today"


def BarChart(
    bars: list[Bar],
    *,
    height: int = 140,
    bar_color: str = "",
    highlight_color: str = "",
    empty_hint: str = "No activity yet",
    currency_axis: bool = True,
) -> ft.Control:
    """Responsive bar chart: rounded bars on a baseline with axis labels.

    Bars share a fixed pixel height area and grow from the bottom. Values are
    rendered above the tallest bar and short labels below each bar.
    """
    bars = [b for b in bars if True]  # keep zero bars for axis continuity
    max_val = max((b.value for b in bars), default=0.0)

    if max_val <= 0:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.BAR_CHART, size=36, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(empty_hint, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            height=height + 24,
            alignment=ft.Alignment.CENTER,
        )

    base = bar_color or ft.Colors.PRIMARY
    hi = highlight_color or ft.Colors.TERTIARY

    columns: list[ft.Control] = []
    for b in bars:
        # Guarantee a visible sliver for a non-zero-but-tiny value.
        frac = (b.value / max_val) if max_val else 0
        bar_h = max(4, round(frac * height))
        color = hi if b.highlight else base

        value_text = ft.Text(
            money_short(b.value) if b.value > 0 else "",
            size=10,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        )

        columns.append(
            ft.Column(
                [
                    value_text,
                    ft.Container(
                        width=18,
                        height=bar_h,
                        bgcolor=color,
                        border_radius=ft.BorderRadius.only(top_left=5, top_right=5),
                    ),
                    ft.Text(
                        b.label,
                        size=11,
                        weight=ft.FontWeight.W_600 if b.highlight else ft.FontWeight.NORMAL,
                        color=ft.Colors.ON_SURFACE if b.highlight else ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                tight=True,
            )
        )

    # Baseline under the bars.
    baseline = ft.Container(height=1, bgcolor=ft.Colors.OUTLINE_VARIANT)

    return ft.Column(
        [
            ft.Row(
                columns,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            baseline,
        ],
        spacing=0,
    )
