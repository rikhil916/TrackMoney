"""Categories tab: list categories with totals, plus add/edit/delete.

The list is a pure builder; the add/edit form lives in ``CategoryDialog`` and
delete uses a confirmation dialog. All mutations report back via callbacks so
the controller can refresh every tab that shows category data.
"""

from __future__ import annotations

import flet as ft

from components.cards import CategoryRow, EmptyState
from database import Database
from models import Category
from utils import FIELD_BORDER, resolve_icon

# Palette offered in the category form (Material 3-ish accents).
COLOR_CHOICES = [
    "#E85D3F", "#E53935", "#D81B60", "#8E24AA", "#5E35B1",
    "#3949AB", "#1E88E5", "#039BE5", "#00ACC1", "#00897B",
    "#43A047", "#7CB342", "#C0CA33", "#FDD835", "#FB8C00",
    "#6D4C41", "#546E7A", "#3F51B5",
]

# A small curated set of icon keys (must exist in ft.Icons).
ICON_CHOICES = [
    "RESTAURANT", "LOCAL_GROCERY_STORE", "DIRECTIONS_BUS", "SHOPPING_BAG",
    "RECEIPT_LONG", "FAVORITE", "MOVIE", "ACCOUNT_BALANCE", "SAVINGS",
    "FLIGHT", "HOME", "SCHOOL", "FITNESS_CENTER", "PALETTE", "PETS",
    "SMARTPHONE", "LOCAL_CAFE", "CARD_GIFTCARD",
]


class CategoryDialog:
    """Add / edit one category in a modal AlertDialog."""

    def __init__(self, page: ft.Page, db: Database, category: Category | None = None,
                 on_saved=None) -> None:
        self.page = page
        self.db = db
        self.category = category
        self.on_saved = on_saved

        self.name = category.name if category else ""
        self.color = category.color if category else COLOR_CHOICES[0]
        self.icon = category.icon if category else ICON_CHOICES[0]

        self._build()

    # ------------------------------------------------------------- UI --

    def _build(self) -> None:
        self.name_field = ft.TextField(
            label="Name",
            value=self.name,
            max_length=40,
            on_change=self._on_name,
            border=FIELD_BORDER,
        )

        # Colour swatches (selected one shows a check).
        self._swatches = ft.Row(
            [self._swatch(c) for c in COLOR_CHOICES],
            spacing=8,
            wrap=True,
        )

        # Icon grid.
        self._icons = ft.Row(
            [self._icon_btn(k) for k in ICON_CHOICES],
            spacing=8,
            wrap=True,
        )

        self.dialog = ft.AlertDialog(
            title=ft.Text("Edit category" if self.category else "New category"),
            content=ft.Column(
                [
                    self.name_field,
                    ft.Text("Colour", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                    self._swatches,
                    ft.Text("Icon", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                    self._icons,
                ],
                spacing=12,
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close()),
                ft.Button("Save", icon=ft.Icons.CHECK, on_click=self._save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _swatch(self, color: str) -> ft.Control:
        selected = color == self.color
        return ft.GestureDetector(
            content=ft.Container(
                content=ft.Icon(ft.Icons.CHECK, size=16, color=ft.Colors.WHITE) if selected
                else None,
                width=32, height=32, border_radius=8, bgcolor=color,
                alignment=ft.Alignment.CENTER,
                border=ft.Border.all(2, ft.Colors.ON_SURFACE) if selected else None,
            ),
            on_tap=self._make_pick_color(color),
        )

    def _make_pick_color(self, color: str):
        def handler(e):
            self.color = color
            self._swatches.controls = [self._swatch(c) for c in COLOR_CHOICES]
            self.page.update()
        return handler

    def _icon_btn(self, key: str) -> ft.Control:
        selected = key == self.icon
        return ft.GestureDetector(
            content=ft.Container(
                content=ft.Icon(resolve_icon(key), size=20,
                                color=ft.Colors.ON_PRIMARY_CONTAINER if selected
                                else ft.Colors.ON_SURFACE_VARIANT),
                width=40, height=40, border_radius=10,
                bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                alignment=ft.Alignment.CENTER,
            ),
            on_tap=self._make_pick_icon(key),
        )

    def _make_pick_icon(self, key: str):
        def handler(e):
            self.icon = key
            self._icons.controls = [self._icon_btn(k) for k in ICON_CHOICES]
            self.page.update()
        return handler

    # ------------------------------------------------------- open/close --

    def open(self) -> None:
        """Show the add/edit dialog through Flet's dialog portal."""
        self.page.show_dialog(self.dialog)

    def close(self) -> None:
        """Dismiss the dialog (top-most)."""
        self.page.pop_dialog()
        self.page.update()

    # ---------------------------------------------------------- events --

    def _on_name(self, e) -> None:
        self.name = e.control.value or ""
        self.name_field.error = None

    def _save(self, e) -> None:
        name = self.name.strip()
        if not name:
            self.name_field.error = "Name cannot be empty"
            self.page.update()
            return
        if self.db.category_name_exists(name, exclude_id=self.category.id if self.category else None):
            self.name_field.error = "A category with this name already exists"
            self.page.update()
            return

        if self.category is not None:
            self.db.update_category(self.category.id, name, self.color, self.icon)
        else:
            self.db.create_category(name, self.color, self.icon)

        self.close()
        if self.on_saved:
            self.on_saved()


def build_categories(db: Database, *, on_add, on_edit, on_delete) -> ft.Control:
    """List every category with totals and per-row actions."""
    cats = db.list_categories()

    header = ft.Row(
        [
            ft.Text("Categories", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
            ft.Button("Add", icon=ft.Icons.ADD, on_click=on_add),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    if not cats:
        body: ft.Control = EmptyState(
            ft.Icons.CATEGORY_OUTLINED,
            "No categories",
            "Create a category to start tracking your money.",
        )
    else:
        body = ft.Column(
            [
                CategoryRow(
                    c,
                    on_edit=_bind(on_edit, c),
                    on_delete=_bind(on_delete, c),
                )
                for c in cats
            ],
            spacing=10,
        )

    return ft.Container(
        content=ft.Column([header, body], spacing=16),
        padding=16,
    )


def _bind(fn, cat: Category):
    """Return a handler that passes this category to fn."""
    def handler(e, _c=cat):
        fn(_c)
    return handler


def confirm_delete_category(page: ft.Page, db: Database, category: Category, on_done) -> None:
    """Ask before deleting; warn that its entries go too."""
    count = db.count_category_entries(category.id)
    detail = (
        f"This will also delete {count} entr{'y' if count == 1 else 'ies'} in "
        f"\u201c{category.name}\u201d. This cannot be undone."
        if count else f"\u201c{category.name}\u201d has no entries."
    )

    def on_confirm(e):
        page.pop_dialog()          # dismiss the confirm dialog first
        db.delete_category(category.id, delete_entries=True)
        if on_done:
            on_done()

    dlg = ft.AlertDialog(
        title=ft.Text(f"Delete {category.name}?"),
        content=ft.Text(detail),
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
