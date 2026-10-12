"""TrackMoney — entry point and app controller.

Wires the SQLite data layer to three Flet tabs (Dashboard, Categories,
History) behind a Material 3 bottom NavigationBar, with a prominent FAB for
adding entries and a light/dark theme toggle.
"""

from __future__ import annotations

from datetime import date

import flet as ft

from database import Database
from models import EntryType
from utils import db_path
from views.add_entry import AddEntrySheet
from views.categories import (
    CategoryDialog,
    build_categories,
    confirm_delete_category,
)
from views.dashboard import build_dashboard
from views.history import build_history, confirm_delete_entry


class TrackMoneyApp:
    """Holds app state and re-renders the active tab on any change."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.db = Database(db_path())

        # UI state.
        self.tab = 0
        self.period = "month"          # dashboard summary window
        self.pie_type = EntryType.SPENT  # donut shows spent or saved
        self.history_filter = "all"     # all / spent / saved
        self.dark = False

        self._setup_page()

    # ---------------------------------------------------------- page setup --

    def _setup_page(self) -> None:
        p = self.page
        p.title = "TrackMoney"
        p.theme_mode = ft.ThemeMode.LIGHT
        p.theme = ft.Theme(color_scheme_seed="#6750A4", use_material3=True)
        p.vertical_alignment = ft.MainAxisAlignment.START
        p.window.width = 420
        p.window.height = 860
        p.window.min_width = 360
        p.window.min_height = 600

        self.theme_btn = ft.IconButton(
            ft.Icons.DARK_MODE, tooltip="Toggle theme", on_click=self._toggle_theme
        )

        self.nav = ft.NavigationBar(
            selected_index=self.tab,
            on_change=self._on_nav,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.DASHBOARD_OUTLINED,
                    selected_icon=ft.Icons.DASHBOARD,
                    label="Dashboard",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.CATEGORY_OUTLINED,
                    selected_icon=ft.Icons.CATEGORY,
                    label="Categories",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.HISTORY,
                    label="History",
                ),
            ],
        )

        self.fab = ft.FloatingActionButton(
            icon=ft.Icons.ADD, tooltip="Add entry", on_click=self._add_entry
        )

        # Scrollable area that holds the active tab's view. ListView gives us
        # vertical scrolling so long content (many entries/categories) is
        # reachable instead of clipped.
        self.scroll = ft.ListView(expand=True, spacing=0, padding=0)
        self.content = ft.Container(content=self.scroll, expand=True)

        p.views.append(
            ft.View(
                route="/",
                appbar=ft.AppBar(
                    title=ft.Text("TrackMoney", weight=ft.FontWeight.BOLD),
                    actions=[self.theme_btn],
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                ),
                navigation_bar=self.nav,
                floating_action_button=self.fab,
                controls=[self.content],
            )
        )
        self.render()

    # ------------------------------------------------------------ routing --

    def _on_nav(self, e) -> None:
        self.tab = e.control.selected_index
        self.render()

    def _toggle_theme(self, e) -> None:
        self.dark = not self.dark
        self.page.theme_mode = ft.ThemeMode.DARK if self.dark else ft.ThemeMode.LIGHT
        self.theme_btn.icon = ft.Icons.LIGHT_MODE if self.dark else ft.Icons.DARK_MODE
        self.page.update()

    # ------------------------------------------------------------- render --

    def render(self) -> None:
        """Rebuild the content area for the current tab and state."""
        if self.tab == 0:
            view = build_dashboard(
                self.db,
                period=self.period,
                pie_type=self.pie_type,
                on_period_change=self._set_period,
                on_pie_type_change=self._set_pie_type,
            )
        elif self.tab == 1:
            view = build_categories(
                self.db,
                on_add=self._add_category,
                on_edit=self._edit_category,
                on_delete=self._delete_category,
            )
        else:
            view = build_history(
                self.db,
                type_filter=self.history_filter,
                on_edit=self._edit_entry,
                on_delete=self._delete_entry,
                on_filter_change=self._set_history_filter,
            )

        # Populate the scrollable ListView with the active tab's view.
        self.scroll.controls = [view]
        self.page.update()

    # ------------------------------------------------------- state setters --

    def _set_period(self, period: str) -> None:
        self.period = period
        self.render()

    def _set_pie_type(self, t: EntryType) -> None:
        self.pie_type = t
        self.render()

    def _set_history_filter(self, f: str) -> None:
        self.history_filter = f
        self.render()

    # --------------------------------------------------------- entry CRUD --

    def _add_entry(self, e) -> None:
        AddEntrySheet(self.page, self.db, on_saved=self.render).open()

    def _edit_entry(self, entry) -> None:
        AddEntrySheet(self.page, self.db, entry=entry, on_saved=self.render).open()

    def _delete_entry(self, entry) -> None:
        confirm_delete_entry(self.page, self.db, entry, on_done=self.render)

    # ------------------------------------------------------- category CRUD --

    def _add_category(self, e=None) -> None:
        CategoryDialog(self.page, self.db, on_saved=self.render).open()

    def _edit_category(self, category) -> None:
        CategoryDialog(self.page, self.db, category=category, on_saved=self.render).open()

    def _delete_category(self, category) -> None:
        confirm_delete_category(self.page, self.db, category, on_done=self.render)


def main(page: ft.Page) -> None:
    TrackMoneyApp(page)


if __name__ == "__main__":
    ft.run(main)
