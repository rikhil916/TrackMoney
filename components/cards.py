"""Reusable presentational widgets shared across views."""

from __future__ import annotations

from datetime import date

import flet as ft

from models import Category, Entry, EntryType
from utils import date_label, money, resolve_icon


def SummaryCard(title: str, amount: str, icon: ft.IconData, color: str, subtitle: str = "") -> ft.Control:
    """Top-of-dashboard stat card: big amount, icon, caption."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, size=22, color=ft.Colors.ON_PRIMARY_CONTAINER),
                    width=44,
                    height=44,
                    border_radius=12,
                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    [
                        ft.Text(title, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(amount, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
        padding=14,
        border_radius=16,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        expand=True,
    )


def EmptyState(icon: ft.IconData, title: str, message: str) -> ft.Control:
    """Friendly placeholder shown when a list has no data yet."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(icon, size=48, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(title, size=16, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE),
                ft.Text(
                    message,
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        padding=32,
        alignment=ft.Alignment.CENTER,
    )


def CategoryRow(category: Category, on_edit, on_delete) -> ft.Control:
    """A category tile showing its colour, icon, name and totals."""
    total = category.total
    return ft.Container(
        content=ft.Row(
            [
                _category_dot(category),
                ft.Column(
                    [
                        ft.Text(category.name, size=15, weight=ft.FontWeight.W_600,
                                color=ft.Colors.ON_SURFACE, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(
                            _category_caption(category),
                            size=12, color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    expand=True,
                ),
                ft.Text(money(total), size=15, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE),
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_size=20, tooltip="Edit",
                                      on_click=on_edit, icon_color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=20, tooltip="Delete",
                                      on_click=on_delete, icon_color=ft.Colors.ON_SURFACE_VARIANT),
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
        padding=12,
        border_radius=14,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
    )


def _category_dot(category: Category) -> ft.Control:
    """Rounded colour chip with the category's icon on top."""
    return ft.Container(
        content=ft.Icon(resolve_icon(category.icon), size=20, color=ft.Colors.ON_PRIMARY_CONTAINER),
        width=40,
        height=40,
        border_radius=12,
        bgcolor=category.color,
        alignment=ft.Alignment.CENTER,
    )


def _category_caption(category: Category) -> str:
    parts = []
    if category.total_spent:
        parts.append(f"spent {money(category.total_spent)}")
    if category.total_saved:
        parts.append(f"saved {money(category.total_saved)}")
    return " \u00b7 ".join(parts) if parts else "No entries yet"


def EntryRow(entry: Entry, on_edit, on_delete) -> ft.Control:
    """A history tile: category dot, name, note, date, signed amount, actions."""
    is_spent = entry.type is EntryType.SPENT
    sign = "\u2212" if is_spent else "+"  # minus / plus
    amount_color = ft.Colors.ERROR if is_spent else ft.Colors.GREEN
    type_chip = ft.Container(
        content=ft.Text(entry.type.label, size=11, weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT),
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )

    return ft.Container(
        content=ft.Row(
            [
                _category_dot(entry_to_dot_source(entry)),
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(entry.category_name, size=15, weight=ft.FontWeight.W_600,
                                        color=ft.Colors.ON_SURFACE, max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                                type_chip,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=8,
                        ),
                        ft.Text(
                            f"{date_label(entry.entry_date)}"
                            + (f" \u00b7 {entry.note}" if entry.note else ""),
                            size=12, color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=3,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    expand=True,
                ),
                ft.Text(f"{sign}{money(entry.amount)}", size=15, weight=ft.FontWeight.BOLD,
                        color=amount_color),
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_size=20, tooltip="Edit",
                                      on_click=on_edit, icon_color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=20, tooltip="Delete",
                                      on_click=on_delete, icon_color=ft.Colors.ON_SURFACE_VARIANT),
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
        padding=12,
        border_radius=14,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
    )


def entry_to_dot_source(entry: Entry) -> Category:
    """Adapt an Entry to the shape _category_dot expects (colour + icon).."""
    return Category(
        id=entry.category_id, name=entry.category_name,
        color=entry.category_color, icon=entry.category_icon,
    )
