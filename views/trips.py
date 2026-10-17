"""Trips tab: list of shared trips, create, join-by-code.

Refresh: manual Refresh button + 5s auto-poll while the screen is open.
Polling is driven by the app (start/stop on tab enter/leave).
"""

from __future__ import annotations

import flet as ft
from backend.money import format_inr
from backend.models import Trip


def _status_chip(trip: Trip) -> ft.Chip:
    open_ = trip.is_open
    return ft.Chip(
        label=ft.Text("Open" if open_ else "Closed"),
        leading=ft.Icon(ft.Icons.LOCK_OPEN if open_ else ft.Icons.LOCK_OUTLINE,
                        size=14),
        bgcolor=ft.Colors.PRIMARY_CONTAINER if open_ else ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )


def build_trips_list(*, trips: list[Trip], totals: dict[str, int],
                     action_needed: dict[str, int], loading=False,
                     error="", on_open, on_refresh, on_create, on_join) -> ft.Control:
    if loading and not trips:
        return ft.Container(
            content=ft.Column(
                [ft.ProgressRing(), ft.Text("Loading trips…")],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=32, alignment=ft.Alignment.CENTER)

    cards: list[ft.Control] = []
    for t in trips:
        dot = action_needed.get(t.id, 0) > 0
        cards.append(ft.Card(content=ft.ListTile(
            leading=ft.CircleAvatar(content=ft.Text(t.name[:1].upper())),
            title=ft.Row([
                ft.Text(t.name, weight=ft.FontWeight.BOLD, expand=True),
                ft.Container(width=10, height=10, border_radius=5,
                             bgcolor=ft.Colors.ERROR) if dot else ft.Container(),
            ]),
            subtitle=ft.Text(
                f"{format_inr(totals.get(t.id, 0))} total"
                + (f"  •  {action_needed[t.id]} need you" if dot else "")
                + ("\n🔒 closed" if not t.is_open else "")),
            trailing=_status_chip(t),
            on_click=lambda e, tid=t.id: on_open(tid),
        )))

    if not cards and not loading:
        cards.append(ft.Card(content=ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.LUGGAGE, size=48,
                        color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("No trips yet", weight=ft.FontWeight.BOLD),
                ft.Text("Create one or join with a 6-letter code.",
                        color=ft.Colors.ON_SURFACE_VARIANT),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
            padding=24)))

    body = ft.Column([
        ft.Row([
            ft.Button("New trip", icon=ft.Icons.ADD, on_click=lambda e: on_create()),
            ft.OutlinedButton("Join code", icon=ft.Icons.KEY,
                              on_click=lambda e: on_join()),
            ft.IconButton(ft.Icons.REFRESH, tooltip="Refresh",
                          on_click=lambda e: on_refresh()),
        ], alignment=ft.MainAxisAlignment.CENTER),
        ft.Text(error, color=ft.Colors.ERROR) if error else ft.Container(),
        *cards,
    ], spacing=10, tight=True)

    return ft.ListView([body], expand=True, spacing=0, padding=0)


def trip_form_dialog(*, on_submit) -> tuple[ft.AlertDialog, dict]:
    from utils import FIELD_BORDER
    name = ft.TextField(label="Trip name", border=FIELD_BORDER)
    dest = ft.TextField(label="Destination (optional)", border=FIELD_BORDER)
    desc = ft.TextField(label="Description (optional)", border=FIELD_BORDER,
                        multiline=True, min_lines=1, max_lines=3)
    err = ft.Text("", color=ft.Colors.ERROR)

    def submit(e):
        try:
            if not (name.value or "").strip():
                raise ValueError("trip name cannot be empty")
            on_submit({"name": name.value or "",
                       "destination": dest.value or "",
                       "description": desc.value or ""})
        except ValueError as exc:
            err.value = str(exc)
            err.update()

    dlg = ft.AlertDialog(
        title=ft.Text("New trip"),
        content=ft.Column([name, dest, desc, err], tight=True, spacing=10),
        actions=[ft.TextButton("Cancel"),
                 ft.Button("Create", on_click=submit)],
        actions_alignment=ft.MainAxisAlignment.END, modal=True)
    return dlg, {"cancel": dlg.actions[0]}


def join_code_dialog(*, on_submit) -> ft.AlertDialog:
    from utils import FIELD_BORDER
    code = ft.TextField(label="6-letter join code", border=FIELD_BORDER,
                        capitalization=ft.TextCapitalization.CHARACTERS)
    err = ft.Text("", color=ft.Colors.ERROR)

    def submit(e):
        try:
            code_val = (code.value or "").strip().upper()
            if len(code_val) != 6:
                raise ValueError("join codes are exactly 6 characters")
            on_submit(code_val)
        except ValueError as exc:
            err.value = str(exc)
            err.update()

    return ft.AlertDialog(
        title=ft.Text("Join with code"),
        content=ft.Column([code, err], tight=True, spacing=10),
        actions=[ft.TextButton("Cancel"),
                 ft.Button("Join", on_click=submit)],
        actions_alignment=ft.MainAxisAlignment.END, modal=True)
