"""History tab: every entry, newest first, with edit and delete actions."""

from __future__ import annotations

import flet as ft

from components.cards import EmptyState, EntryRow
from database import Database
from models import Entry, EntryType
from utils import seg_selected


def build_history(db: Database, *, type_filter: str, on_edit, on_delete, on_filter_change) -> ft.Control:
    """List entries (optionally filtered by type) with per-row actions."""
    entries = db.list_entries()

    # Client-side filter (all / spent / saved).
    if type_filter in (EntryType.SPENT.value, EntryType.SAVED.value):
        entries = [e for e in entries if e.type.value == type_filter]

    filter_toggle = ft.SegmentedButton(
        segments=[
            ft.Segment(value="all", label="All"),
            ft.Segment(value=EntryType.SPENT.value, label="Spent"),
            ft.Segment(value=EntryType.SAVED.value, label="Saved"),
        ],
        selected=[type_filter],
        on_change=lambda e: on_filter_change(seg_selected(e, type_filter)),
    )

    header = ft.Row(
        [
            ft.Text("History", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
            filter_toggle,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    if not entries:
        if type_filter == "all":
            body: ft.Control = EmptyState(
                ft.Icons.HISTORY,
                "No entries yet",
                "Tap the + button to log your first entry.",
            )
        else:
            body = EmptyState(
                ft.Icons.FILTER_LIST,
                f"No {type_filter} entries",
                "Try a different filter or add a new entry.",
            )
    else:
        body = ft.Column(
            [
                EntryRow(e, on_edit=_bind(on_edit, e), on_delete=_bind(on_delete, e))
                for e in entries
            ],
            spacing=10,
        )

    return ft.Container(
        content=ft.Column([header, body], spacing=16),
        padding=16,
    )


def _bind(fn, entry: Entry):
    def handler(e, _e=entry):
        fn(_e)
    return handler


def confirm_delete_entry(page: ft.Page, db: Database, entry: Entry, on_done) -> None:
    """Confirm deleting a single entry."""

    def on_confirm(e):
        page.pop_dialog()          # dismiss the confirm dialog first
        db.delete_entry(entry.id)
        if on_done:
            on_done()

    dlg = ft.AlertDialog(
        title=ft.Text("Delete entry?"),
        content=ft.Text(
            f"{entry.category_name} \u00b7 {entry.type.label.lower()} \u00b7 "
            f"\u20b9{entry.amount:,.2f} will be removed."
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: _close(page, dlg)),
            ft.Button("Delete", icon=ft.Icons.DELETE_OUTLINE, bgcolor=ft.Colors.ERROR,
                      color=ft.Colors.ON_ERROR, on_click=on_confirm),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)


def _close(page: ft.Page, dlg) -> None:
    """Dismiss a confirm dialog via the dialog portal."""
    page.pop_dialog()
    page.update()
