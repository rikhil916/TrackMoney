"""Formatting helpers shared across views (amounts, dates, icons)."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import flet as ft

RUPEE = "\u20b9"  # ₹

# Shared rounded-border for text/dropdown fields (flet 1.0 moved border_radius
# on form fields to the `border` property).
FIELD_BORDER = ft.OutlineInputBorder(border_radius=ft.BorderRadius.all(12))


def seg_selected(e, default: str = "") -> str:
    """Return the newly-selected value of a SegmentedButton event.

    Flet does not sync a control's properties from the event payload before the
    handler runs, so ``e.control.selected`` is stale here. The fresh selection
    arrives in ``e.data`` (a list of segment values, possibly JSON-encoded).
    """
    data: Any = getattr(e, "data", None)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            data = [data] if data else []
    if isinstance(data, list) and data:
        return str(data[0])
    if isinstance(data, str) and data:
        return data
    # Fallback: read whatever the control currently reports.
    selected = getattr(e.control, "selected", None)
    if selected:
        return str(selected[0])
    return default


def money(amount: float) -> str:
    """Format an amount as ₹ with thousands separators and 2 decimals."""
    sign = "-" if amount < 0 else ""
    return f"{sign}{RUPEE}{abs(amount):,.2f}"


def money_short(amount: float) -> str:
    """Compact ₹ format for tight chart labels (₹1.2k, ₹34k, ₹1.5L)."""
    a = abs(amount)
    sign = "-" if amount < 0 else ""
    if a >= 1_00_00_000:  # crore
        return f"{sign}{RUPEE}{a / 1_00_00_000:.1f}Cr"
    if a >= 1_00_000:  # lakh
        return f"{sign}{RUPEE}{a / 1_00_000:.1f}L"
    if a >= 1_000:  # thousand
        return f"{sign}{RUPEE}{a / 1_000:.1f}k"
    return f"{sign}{RUPEE}{a:,.0f}"


def date_label(d: date, *, today: date | None = None) -> str:
    """Friendly date string: 'Today', 'Yesterday', or '12 Oct 2026'."""
    t = today or date.today()
    if d == t:
        return "Today"
    if d == date.fromordinal(t.toordinal() - 1):
        return "Yesterday"
    return d.strftime("%d %b %Y")


def weekday_label(d: date) -> str:
    """Single-letter weekday for chart axes (M T W T F S S)."""
    return "MTWTFSS"[d.weekday()]


def db_path() -> str:
    """Resolve where the SQLite file lives on this platform.

    Uses $TRACKMONEY_DB if set, otherwise a per-user data dir so the app works
    offline on desktop, web and Android alike.
    """
    env = os.environ.get("TRACKMONEY_DB")
    if env:
        return env

    if sys.platform == "android":
        # On Android, Flet exposes the app's private storage via $FLET_APP_STORAGE.
        base = os.environ.get("FLET_APP_STORAGE", "/data/data/app")
        root = os.path.join(base, "TrackMoney")
    else:
        root = os.path.join(Path.home(), ".trackmoney")

    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "trackmoney.db")


def resolve_icon(key: str | None, fallback: ft.IconData = ft.Icons.CATEGORY) -> ft.IconData:
    """Look up a stored material icon name, falling back safely."""
    if key:
        icon = getattr(ft.Icons, key, None)
        if icon is not None:
            return icon
    return fallback
