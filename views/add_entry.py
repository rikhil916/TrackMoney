"""Add / edit an entry, shown as a Material bottom sheet.

The sheet owns its form controls and validates input before writing through
the data layer. It reports back to the app via a single ``on_saved`` callback
so the caller can refresh the dashboard immediately.
"""

from __future__ import annotations

from datetime import date

import flet as ft

from database import Database
from models import Entry, EntryDraft, EntryType
from utils import FIELD_BORDER, seg_selected


class AddEntrySheet:
    """Bottom-sheet form for creating or editing one entry."""

    def __init__(
        self,
        page: ft.Page,
        db: Database,
        *,
        entry: Entry | None = None,
        on_saved=None,
    ) -> None:
        self.page = page
        self.db = db
        self.entry = entry
        self.on_saved = on_saved

        # Prefill for edit, blank for create.
        draft = EntryDraft()
        if entry is not None:
            draft = EntryDraft(
                id=entry.id,
                category_id=entry.category_id,
                amount=str(entry.amount),
                type=entry.type,
                note=entry.note or "",
                entry_date=entry.entry_date,
            )
        self.draft = draft
        self._parsed_amount: float = 0.0

        self._build_controls()

    # ------------------------------------------------------------- UI --

    def _build_controls(self) -> None:
        cats = self.db.list_categories()

        # Category dropdown (keys are stringified ids).
        self.category_dd = ft.Dropdown(
            label="Category",
            value=str(self.draft.category_id) if self.draft.category_id else None,
            options=[
                ft.DropdownOption(key=str(c.id), text=c.name) for c in cats
            ],
            on_select=self._on_category_select,
            border=FIELD_BORDER,
        )

        # Amount (numeric, > 0 enforced on save; filter keeps the field clean).
        self.amount_field = ft.TextField(
            label="Amount",
            value=self.draft.amount,
            prefix="\u20b9",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.InputFilter(regex_string=r"^\d*\.?\d*$", allow=True),
            on_change=self._on_amount_change,
            border=FIELD_BORDER,
        )

        # Spent / Saved toggle.
        self.type_seg = ft.SegmentedButton(
            segments=[
                ft.Segment(value=EntryType.SPENT.value, icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                           label=EntryType.SPENT.label),
                ft.Segment(value=EntryType.SAVED.value, icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                           label=EntryType.SAVED.label),
            ],
            selected=[self.draft.type.value],
            on_change=self._on_type_change,
        )

        # Optional note.
        self.note_field = ft.TextField(
            label="Note (optional)",
            value=self.draft.note,
            max_length=120,
            border=FIELD_BORDER,
        )

        # Date row: readable label + button that opens a DatePicker.
        self.date_label_text = ft.Text(self._format_date(), size=14, color=ft.Colors.ON_SURFACE)
        date_row = ft.Row(
            [
                ft.Icon(ft.Icons.CALENDAR_TODAY, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("Date", size=13, color=ft.Colors.ON_SURFACE_VARIANT, expand=True),
                self.date_label_text,
                ft.TextButton("Change", on_click=self._open_date_picker),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.save_btn = ft.Button(
            "Save entry",
            icon=ft.Icons.CHECK,
            on_click=self._save,
        )

        cancel_btn = ft.TextButton("Cancel", on_click=lambda e: self.close())

        # AlertDialog centers on screen (the user asked for a centred form,
        # not a bottom sheet).
        self.sheet = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Edit entry" if self.entry else "New entry",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ON_SURFACE,
            ),
            content=ft.Column(
                [
                    self.category_dd,
                    self.amount_field,
                    ft.Text("Type", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                    self.type_seg,
                    self.note_field,
                    date_row,
                ],
                spacing=14,
                tight=True,
            ),
            actions=[cancel_btn, self.save_btn],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # ------------------------------------------------------- open/close --

    def open(self) -> None:
        """Show the entry form as a centred dialog (Flet 1.0 dialog portal)."""
        self.page.show_dialog(self.sheet)

    def close(self, dialog=None) -> None:
        """Dismiss the top-most dialog (the form, or a nested date picker)."""
        self.page.pop_dialog()
        self.page.update()

    # ---------------------------------------------------------- events --

    def _on_category_select(self, e) -> None:
        self.draft.category_id = int(e.control.value)
        self.category_dd.error = None

    def _on_amount_change(self, e) -> None:
        self.draft.amount = e.control.value or ""
        self.amount_field.error = None

    def _on_type_change(self, e) -> None:
        # SegmentedButton (single selection): fresh value comes from e.data.
        self.draft.type = EntryType(seg_selected(e, self.draft.type.value))

    def _open_date_picker(self, e) -> None:
        picker = ft.DatePicker(
            value=self.draft.entry_date,
            on_change=self._on_date_picked,
        )
        # Nested dialog: show_dialog stacks it above the entry form.
        self.page.show_dialog(picker)

    def _on_date_picked(self, e) -> None:
        if e.control.value:
            self.draft.entry_date = e.control.value
            self.date_label_text.value = self._format_date()
        # Dismiss the picker (top-most dialog). show_dialog already wired its
        # on_dismiss to remove it from the portal after the close animation.
        self.page.pop_dialog()
        self.page.update()

    def _format_date(self) -> str:
        return self.draft.entry_date.strftime("%a, %d %b %Y")

    def _validate(self) -> bool:
        """Return True when the form is valid; otherwise surface errors."""
        ok = True

        if not self.draft.category_id:
            self.category_dd.error = "Choose a category"
            ok = False
        else:
            self.category_dd.error = None

        raw = (self.draft.amount or "").strip().replace(",", "")
        try:
            amount = float(raw) if raw else 0.0
        except ValueError:
            amount = 0.0

        if not raw:
            self.amount_field.error = "Enter an amount"
            ok = False
        elif amount <= 0:
            self.amount_field.error = "Amount must be greater than 0"
            ok = False
        else:
            self.amount_field.error = None

        self._parsed_amount = amount if ok else 0.0
        return ok

    def _save(self, e) -> None:
        if not self._validate():
            self.page.update()
            return

        amount = self._parsed_amount
        note = (self.note_field.value or "").strip() or None

        if self.entry is not None:
            self.db.update_entry(
                self.entry.id, self.draft.category_id, amount,
                self.draft.type, self.draft.entry_date, note,
            )
        else:
            self.db.add_entry(
                self.draft.category_id, amount, self.draft.type,
                self.draft.entry_date, note,
            )

        self.close()
        if self.on_saved:
            self.on_saved()
