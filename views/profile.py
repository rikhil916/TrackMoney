"""Profile screen: view/edit name+username, see phone, log out."""

from __future__ import annotations

import flet as ft
from utils import FIELD_BORDER


def build_profile(*, profile, on_save, on_logout, on_retry=None,
                  error="") -> ft.Control:
    if profile is None:
        # Logged in but the profile row isn't readable yet (e.g. first login
        # right after email confirmation). Never crash — offer a retry.
        return ft.Container(content=ft.Column([
            ft.ProgressRing(),
            ft.Text("Setting up your profile…", weight=ft.FontWeight.BOLD),
            ft.Text(error or "This usually takes a few seconds.",
                    color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Button("Retry", icon=ft.Icons.REFRESH,
                      on_click=lambda e: on_retry() if on_retry else None),
            ft.OutlinedButton("Log out", icon=ft.Icons.LOGOUT,
                              on_click=lambda e: on_logout()),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12, tight=True),
            padding=32, alignment=ft.Alignment.CENTER)

    name = ft.TextField(label="Full name", value=profile.name,
                        border=FIELD_BORDER)
    username = ft.TextField(label="Username", value=profile.username,
                            border=FIELD_BORDER)

    def save(e):
        on_save(name.value or "", username.value or "")

    rows: list[ft.Control] = [
        ft.ListTile(
            leading=ft.CircleAvatar(
                content=ft.Text((profile.name or "?")[:1].upper())),
            title=ft.Text(profile.name or "—",
                          weight=ft.FontWeight.BOLD),
            subtitle=ft.Text(f"@{profile.username}\n{profile.phone}"),
        ),
        name, username,
        ft.Text(error, color=ft.Colors.ERROR) if error else ft.Container(),
        ft.Button("Save changes", icon=ft.Icons.SAVE, on_click=save),
        ft.OutlinedButton("Log out", icon=ft.Icons.LOGOUT, on_click=lambda e: on_logout()),
        ft.Text("Phone numbers can't be changed in v1. Personal categories "
                "and entries stay on this device, separated per user.",
                color=ft.Colors.ON_SURFACE_VARIANT, size=12),
    ]
    return ft.Container(content=ft.Column(rows, spacing=12, tight=True), padding=16)
