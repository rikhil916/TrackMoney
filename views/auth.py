"""Auth screens: login + sign-up (email confirmation required in v1)."""

from __future__ import annotations

import flet as ft
from utils import FIELD_BORDER


def _field(label: str, *, password=False, hint="", keyboard=None,
           value="", autocorrect=True) -> ft.TextField:
    # Auth fields pass autocorrect=False: phone/browser keyboards otherwise
    # auto-capitalize or "fix" passwords/usernames, making the two password
    # boxes (or the login id) silently differ from what the user typed.
    return ft.TextField(
        label=label, password=password, can_reveal_password=password,
        hint_text=hint or None, value=value,
        keyboard_type=keyboard or ft.KeyboardType.TEXT,
        autocorrect=autocorrect, enable_suggestions=autocorrect,
        smart_quotes_type=False, smart_dashes_type=False,
        border=FIELD_BORDER)


def build_login(*, on_login, on_go_signup, error="",
                initial: dict | None = None) -> ft.Control:
    initial = initial or {}
    login_id = _field("Email or username", autocorrect=False,
                      value=initial.get("login_id", ""))
    pw = _field("Password", password=True, autocorrect=False)

    def submit(e):
        on_login(login_id.value or "", pw.value or "")

    card = ft.Card(content=ft.Container(
        content=ft.Column([
            ft.Text("Welcome back", size=22, weight=ft.FontWeight.BOLD),
            ft.Text("Log in to see your trips on any phone.",
                    color=ft.Colors.ON_SURFACE_VARIANT),
            login_id, pw,
            ft.Text(error, color=ft.Colors.ERROR) if error else ft.Container(),
            ft.Button("Log in", icon=ft.Icons.LOGIN, on_click=submit),
            ft.TextButton("New here? Create an account",
                          on_click=lambda e: on_go_signup()),
        ], spacing=12, tight=True),
        padding=20))
    return ft.Container(content=ft.Column(
        [ft.Container(height=40), card], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=16)


def build_signup(*, on_signup, on_go_login, error="", info="",
                 initial: dict | None = None) -> ft.Control:
    initial = initial or {}
    name = _field("Full name", hint="Aarav Sharma",
                  value=initial.get("name", ""))
    username = _field("Username", hint="3-20 lowercase letters/digits/_",
                      autocorrect=False, value=initial.get("username", ""))
    phone = _field("Phone", hint="10-digit mobile",
                   keyboard=ft.KeyboardType.PHONE,
                   value=initial.get("phone", ""))
    email = _field("Email", keyboard=ft.KeyboardType.EMAIL,
                   autocorrect=False, value=initial.get("email", ""))
    pw = _field("Password", password=True, hint="min 8 characters",
                autocorrect=False)
    confirm = _field("Confirm password", password=True, autocorrect=False)
    # Live match feedback so a keyboard "correction" in one box is visible
    # before tapping Sign up.
    match = ft.Text("", size=12)

    def refresh_match(e=None):
        a, b = pw.value or "", confirm.value or ""
        if not b:
            match.value, match.color = "", ft.Colors.ON_SURFACE_VARIANT
        elif a == b:
            match.value, match.color = "Passwords match ✓", ft.Colors.GREEN
        else:
            match.value, match.color = "Passwords don't match yet", \
                ft.Colors.ORANGE
        match.update()

    pw.on_change = refresh_match
    confirm.on_change = refresh_match

    def submit(e):
        on_signup({"name": name.value or "", "username": username.value or "",
                   "phone": phone.value or "", "email": email.value or "",
                   "password": pw.value or "", "confirm": confirm.value or ""})

    return ft.Container(content=ft.Column([
        ft.Text("Create account", size=22, weight=ft.FontWeight.BOLD),
        ft.Text("Email confirmation required — check your inbox after signing up.",
                color=ft.Colors.ON_SURFACE_VARIANT),
        name, username, phone, email, pw, confirm, match,
        ft.Text(error, color=ft.Colors.ERROR) if error else ft.Container(),
        ft.Text(info, color=ft.Colors.PRIMARY) if info else ft.Container(),
        ft.Button("Sign up", icon=ft.Icons.PERSON_ADD, on_click=submit),
        ft.TextButton("Have an account? Log in",
                      on_click=lambda e: on_go_login()),
    ], spacing=10, tight=True, scroll=ft.ScrollMode.AUTO),
        padding=16)
