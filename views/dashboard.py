"""Dashboard tab: summary cards, donut split, weekly + monthly spend charts.

This module is a pure builder: it takes data + the two pieces of UI state
(selected period, pie type) plus callbacks, and returns a Control tree. The
controller in main.py owns the state and re-renders on change.
"""

from __future__ import annotations

from datetime import date, timedelta

import flet as ft

from components.cards import EmptyState, SummaryCard
from components.charts import Bar, BarChart, DonutChart, Slice
from database import Database
from models import EntryType
from utils import money, seg_selected, weekday_label


def month_bounds(d: date) -> tuple[date, date]:
    """First and last day of d's calendar month."""
    first = d.replace(day=1)
    if first.month == 12:
        nxt = first.replace(year=first.year + 1, month=1)
    else:
        nxt = first.replace(month=first.month + 1)
    return first, nxt - timedelta(days=1)


def period_start(period: str, today: date) -> date:
    """Earliest date (inclusive) for the given period key."""
    if period == "week":
        return today - timedelta(days=6)
    if period == "month":
        return month_bounds(today)[0]
    return date(2000, 1, 1)  # "all"


def build_dashboard(
    db: Database,
    *,
    period: str,
    pie_type: EntryType,
    on_period_change,  # (str) -> None
    on_pie_type_change,  # (EntryType) -> None
) -> ft.Control:
    """Assemble the whole dashboard column for the selected period."""
    today = date.today()
    start = period_start(period, today)
    end = today

    summary = db.summary(start, end)

    # ---- summary cards -------------------------------------------------
    cards = ft.Row(
        [
            SummaryCard("Spent", money(summary.spent), ft.Icons.ARROW_UPWARD, "#E53935"),
            SummaryCard("Saved", money(summary.saved), ft.Icons.ARROW_DOWNWARD, "#43A047"),
        ],
        spacing=12,
        tight=True,
    )

    balance_color = ft.Colors.PRIMARY if summary.balance >= 0 else ft.Colors.ERROR
    balance_card = ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Balance", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(money(summary.balance), size=22, weight=ft.FontWeight.BOLD,
                                color=balance_color),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Icon(
                    ft.Icons.TRENDING_UP if summary.balance >= 0 else ft.Icons.TRENDING_DOWN,
                    size=28, color=balance_color,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=16,
        border_radius=16,
        bgcolor=ft.Colors.PRIMARY_CONTAINER,
    )

    # ---- donut: split by category for the chosen type ------------------
    breakdown = db.category_breakdown(start, end, pie_type)
    slices = [Slice(label=c.name, value=v, color=c.color) for c, v in breakdown]
    total_pie = sum(s.value for s in slices)

    pie_type_toggle = ft.SegmentedButton(
        segments=[
            ft.Segment(value=EntryType.SPENT.value, icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                       label=EntryType.SPENT.label),
            ft.Segment(value=EntryType.SAVED.value, icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                       label=EntryType.SAVED.label),
        ],
        selected=[pie_type.value],
        on_change=lambda e: on_pie_type_change(EntryType(seg_selected(e, pie_type.value))),
    )

    donut = DonutChart(
        slices,
        center_value=money(total_pie),
        center_title=f"total {pie_type.label.lower()}",
        empty_hint=f"No {pie_type.label.lower()} entries yet",
    )

    # ---- weekly (last 7 days) -----------------------------------------
    week_start = today - timedelta(days=6)
    week_days = db.daily_totals(week_start, today)
    week_bars = [
        Bar(label=weekday_label(d.day), value=d.spent, highlight=d.day == today)
        for d in week_days
    ]

    # ---- monthly (current calendar month, by day) ----------------------
    m_start, m_end = month_bounds(today)
    month_days = db.daily_totals(m_start, m_end)
    month_bars = [
        Bar(label=str(d.day.day), value=d.spent, highlight=d.day == today)
        for d in month_days
    ]

    def section(title: str, body: ft.Control) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(title, size=15, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE),
                    body,
                ],
                spacing=12,
            ),
            padding=16,
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        )

    # ---- empty state when there's nothing for the period ---------------
    if summary.is_empty and not slices:
        body: ft.Control = EmptyState(
            ft.Icons.WALLET_OUTLINED,
            "No entries yet",
            "Tap the + button to log your first entry.",
        )
    else:
        body = ft.Column(
            [
                cards,
                balance_card,
                section(
                    f"Where your money goes ({pie_type.label.lower()})",
                    ft.Column([pie_type_toggle, donut], spacing=12,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ),
                section("Last 7 days", BarChart(week_bars, empty_hint="No spend in the last 7 days")),
                section(f"This month ({today.strftime('%b')})",
                        BarChart(month_bars, empty_hint=f"No spend in {today.strftime('%B')}")),
            ],
            spacing=16,
        )

    period_toggle = ft.SegmentedButton(
        segments=[
            ft.Segment(value="week", label="Week"),
            ft.Segment(value="month", label="Month"),
            ft.Segment(value="all", label="All"),
        ],
        selected=[period],
        on_change=lambda e: on_period_change(seg_selected(e, period)),
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Dashboard", size=24, weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ON_SURFACE),
                        period_toggle,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                body,
            ],
            spacing=16,
        ),
        padding=16,
    )
