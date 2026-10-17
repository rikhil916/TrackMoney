"""TrackMoney — entry point and app controller.

Personal tabs (Dashboard/Categories/History) run on local SQLite, scoped per
logged-in user. Trips/Profile run on Supabase via backend/ (UI never touches
the network directly). Trip screens poll every 5s + pull-to-refresh.
"""

from __future__ import annotations

import asyncio

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

try:
    from backend import auth as cloud_auth
    from backend import profiles as cloud_profiles
    from backend import trips as cloud_trips
    from backend.config import get_settings
    from backend.money import format_inr
    CLOUD_AVAILABLE = True
except ImportError:  # pragma: no cover - running without cloud deps
    CLOUD_AVAILABLE = False


class TrackMoneyApp:
    """Holds app state and re-renders the active tab on any change."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.db = Database(db_path())

        # UI state (personal tabs unchanged).
        self.tab = 0
        self.period = "month"
        self.pie_type = EntryType.SPENT
        self.history_filter = "all"
        self.dark = False

        # Cloud state.
        self.user_id: str | None = None
        self.profile = None
        self.cloud_error = ""
        self.auth_mode = "login"  # login | signup | profile
        self.auth_screen_open = False  # True while login/signup/profile shown
        self._login_form: dict = {}
        self._signup_form: dict = {}
        self.cloud_on = CLOUD_AVAILABLE and get_settings().configured \
            if CLOUD_AVAILABLE else False

        # Trips state.
        self.trips: list = []
        self.trip_totals: dict[str, int] = {}
        self.trip_actions: dict[str, int] = {}
        self.trips_loading = False
        self.open_trip_id: str | None = None
        self.trip_view = "detail"  # detail | settlement
        self.trip_data: dict = {}
        self._polling = False

        self._setup_page()
        self._boot_auth()

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
            ft.Icons.DARK_MODE, tooltip="Toggle theme", on_click=self._toggle_theme)
        self.profile_btn = ft.IconButton(
            ft.Icons.ACCOUNT_CIRCLE, tooltip="Profile",
            on_click=self._open_profile)

        self.nav = ft.NavigationBar(
            selected_index=self.tab, on_change=self._on_nav, destinations=[])
        self._rebuild_nav()

        self.fab = ft.FloatingActionButton(
            icon=ft.Icons.ADD, tooltip="Add entry", on_click=self._fab_tap)

        self.scroll = ft.ListView(expand=True, spacing=0, padding=0)
        self.content = ft.Container(content=self.scroll, expand=True)

        p.views.append(ft.View(
            route="/",
            appbar=ft.AppBar(
                title=ft.Text("TrackMoney", weight=ft.FontWeight.BOLD),
                actions=[self.theme_btn, self.profile_btn],
                bgcolor=ft.Colors.SURFACE_CONTAINER),
            navigation_bar=self.nav,
            floating_action_button=self.fab,
            controls=[self.content]))
        self.render()

    def _rebuild_nav(self) -> None:
        dot = any(self.trip_actions.values())
        self.nav.destinations = [
            ft.NavigationBarDestination(
                icon=ft.Icons.DASHBOARD_OUTLINED,
                selected_icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationBarDestination(
                icon=ft.Icons.CATEGORY_OUTLINED,
                selected_icon=ft.Icons.CATEGORY, label="Categories"),
            ft.NavigationBarDestination(
                icon=ft.Icons.HISTORY, label="History"),
            ft.NavigationBarDestination(
                icon=ft.Icons.LUGGAGE_OUTLINED,
                selected_icon=ft.Icons.LUGGAGE,
                label="Trips •" if dot else "Trips"),
        ]
        self.nav.selected_index = self.tab

    # ---------------------------------------------------------------- boot --
    def _boot_auth(self) -> None:
        if not self.cloud_on:
            return
        try:
            sess = cloud_auth.restore_session()
        except Exception:
            sess = None
        if sess:
            self.user_id = sess["user_id"]
            self.db.set_user(self.user_id)
            self._load_profile_quiet()
            self.render()

    def _load_profile_quiet(self) -> None:
        try:
            self.profile = cloud_profiles.get_my_profile()
        except Exception:
            self.profile = None

    def _reload_profile(self) -> None:
        """Retry button on the profile screen when the row wasn't ready."""
        self.cloud_error = ""
        self._load_profile_quiet()
        if self.profile is None:
            self.cloud_error = "Profile still not found — check your connection, then retry."
        self._show_auth_overlay()

    # -------------------------------------------------------------- routing --
    def _on_nav(self, e) -> None:
        self._stop_poll()
        self.tab = e.control.selected_index
        self.open_trip_id = None
        self.auth_screen_open = False  # leaving tab closes profile/login screens
        if self.tab == 3 and self.cloud_on and self.user_id:
            self._refresh_trips()
            self._start_poll("trips")
        self.render()

    def _toggle_theme(self, e) -> None:
        self.dark = not self.dark
        self.page.theme_mode = ft.ThemeMode.DARK if self.dark else ft.ThemeMode.LIGHT
        self.theme_btn.icon = ft.Icons.LIGHT_MODE if self.dark else ft.Icons.DARK_MODE
        self.page.update()

    # --------------------------------------------------------------- render --
    def _needs_auth(self) -> bool:
        """App-wide login gate: when cloud is configured, the whole app
        requires login — personal tabs and trips share the same identity."""
        return self.cloud_on and self.user_id is None

    def render(self) -> None:
        # While login/signup/profile is on screen, keep it there (the 5s trip
        # poll calls render() and must not wipe these screens).
        if self.auth_screen_open and self.tab == 3:
            self._show_auth_overlay()
            return
        if self._needs_auth() and self.tab != 3:
            # Any personal tab without a session falls through to the login
            # gate instead of showing logged-out data.
            self._show_auth_overlay()
            return
        if self.tab == 0:
            view = build_dashboard(
                self.db, period=self.period, pie_type=self.pie_type,
                on_period_change=self._set_period,
                on_pie_type_change=self._set_pie_type)
            self.fab.visible, self.fab.tooltip = True, "Add entry"
        elif self.tab == 1:
            view = build_categories(
                self.db, on_add=self._add_category, on_edit=self._edit_category,
                on_delete=self._delete_category)
            self.fab.visible, self.fab.tooltip = True, "Add category"
        elif self.tab == 2:
            view = build_history(
                self.db, type_filter=self.history_filter,
                on_edit=self._edit_entry, on_delete=self._delete_entry,
                on_filter_change=self._set_history_filter)
            self.fab.visible, self.fab.tooltip = True, "Add entry"
        else:
            view = self._trips_view()
            self.fab.visible = (
                self.cloud_on and self.user_id is not None
                and self.open_trip_id is None)
            self.fab.tooltip = "New trip"
        self._rebuild_nav()
        self.scroll.controls = [view]
        self.page.update()

    # --------------------------------------------------------- state setters --
    def _set_period(self, period: str) -> None:
        self.period = period
        self.render()

    def _set_pie_type(self, t: EntryType) -> None:
        self.pie_type = t
        self.render()

    def _set_history_filter(self, f: str) -> None:
        self.history_filter = f
        self.render()

    # ----------------------------------------------------------- entry CRUD --
    def _fab_tap(self, e) -> None:
        if self.tab == 1:
            self._add_category()
        elif self.tab == 3:
            self._create_trip_dialog()
        else:
            self._add_entry(e)

    def _add_entry(self, e) -> None:
        AddEntrySheet(self.page, self.db, on_saved=self.render).open()

    def _edit_entry(self, entry) -> None:
        AddEntrySheet(self.page, self.db, entry=entry, on_saved=self.render).open()

    def _delete_entry(self, entry) -> None:
        confirm_delete_entry(self.page, self.db, entry, on_done=self.render)

    # -------------------------------------------------------- category CRUD --
    def _add_category(self, e=None) -> None:
        CategoryDialog(self.page, self.db, on_saved=self.render).open()

    def _edit_category(self, category) -> None:
        CategoryDialog(self.page, self.db, category=category,
                       on_saved=self.render).open()

    def _delete_category(self, category) -> None:
        confirm_delete_category(self.page, self.db, category, on_done=self.render)

    # ----------------------------------------------------------------- auth --
    def _open_profile(self, e) -> None:
        if not self.cloud_on:
            self._snack("Cloud not configured — add .env (see SETUP_TRIPS.md)")
            return
        if self.user_id is None:
            self.auth_mode = "login"
        else:
            self.auth_mode = "profile"
            self._load_profile_quiet()
        self._stop_poll()
        self.tab = 3
        self.open_trip_id = None
        self._show_auth_overlay()

    def _show_auth_overlay(self) -> None:
        from views.auth import build_login, build_signup
        from views.profile import build_profile
        self.auth_screen_open = True  # render() keeps this screen until closed
        # App-wide gate: logged-out users only ever see login/signup.
        if self._needs_auth() and self.auth_mode == "profile":
            self.auth_mode = "login"
        if self.auth_mode == "signup":
            view = build_signup(on_signup=self._do_signup,
                                on_go_login=self._go_login,
                                error=self.cloud_error,
                                initial=self._signup_form)
        elif self.auth_mode == "profile" and self.user_id:
            view = build_profile(profile=self.profile, on_save=self._do_save_profile,
                                 on_logout=self._do_logout,
                                 on_retry=self._reload_profile,
                                 error=self.cloud_error)
        else:
            view = build_login(on_login=self._do_login,
                               on_go_signup=self._go_signup,
                               error=self.cloud_error,
                               initial=self._login_form)
        self._rebuild_nav()
        self.scroll.controls = [view]
        self.page.update()

    def _go_login(self) -> None:
        self.auth_mode, self.cloud_error = "login", ""
        self._show_auth_overlay()

    def _go_signup(self) -> None:
        self.auth_mode, self.cloud_error = "signup", ""
        self._show_auth_overlay()

    def _do_login(self, login_id: str, password: str) -> None:
        self._login_form = {"login_id": login_id}  # keep id, never the password
        try:
            r = cloud_auth.login(login_id=login_id, password=password)
            self.user_id = r["user_id"]
            self.db.set_user(self.user_id)
            self._login_form = {}  # clear after success
            self.cloud_error, self.auth_mode = "", "profile"
            self.auth_screen_open = False  # close the login screen
            self._load_profile_quiet()
            if r.get("profile_missing") or self.profile is None:
                self.cloud_error = (
                    "Your login works, but no profile row exists for it "
                    "(this phone/username may belong to another account). "
                    "Tap Retry, or log out and use your original account.")
            self.open_trip_id = None
            self._refresh_trips()
            self._start_poll("trips") if self.tab == 3 else None
            self.render()
        except Exception as exc:
            self.cloud_error = str(exc)
            self._expired_or_error()
            self._show_auth_overlay()

    def _do_signup(self, f: dict) -> None:
        # Keep non-secret fields so an error doesn't wipe the form.
        self._signup_form = {k: f.get(k, "") for k in
                             ("name", "username", "phone", "email")}
        try:
            r = cloud_auth.sign_up(**f)
            if not r.get("confirmed"):
                self.cloud_error = ""
                self.auth_mode = "login"
                self._snack("Account created — confirm your email, then log in.")
                self._show_auth_overlay()
                return
            self.user_id = r["user_id"]
            self.db.set_user(self.user_id)
            self._signup_form = {}  # clear after success
            self.auth_screen_open = False
            self._load_profile_quiet()
            self.tab = 3
            self._refresh_trips()
            self.render()
        except Exception as exc:
            self.cloud_error = str(exc)
            self._show_auth_overlay()

    def _do_save_profile(self, name: str, username: str) -> None:
        try:
            self.profile = cloud_profiles.update_my_profile(name=name,
                                                            username=username)
            self.cloud_error = ""
            self._snack("Profile saved.")
        except Exception as exc:
            self.cloud_error = str(exc)
        self._show_auth_overlay()

    def _do_logout(self) -> None:
        cloud_auth.logout()
        self._stop_poll()
        self.user_id, self.profile = None, None
        self.db.set_user("local")
        self.trips, self.trip_totals, self.trip_actions = [], {}, {}
        self.open_trip_id = None
        self.auth_mode, self.tab = "login", 0
        self.cloud_error = ""
        self.auth_screen_open = True  # show the login gate on next render
        self.render()

    def _expired_or_error(self) -> None:
        if "expired" in (self.cloud_error or "").lower() or \
                "token" in (self.cloud_error or "").lower():
            cloud_auth.logout()
            self.user_id = None
            self.db.set_user("local")
            self.auth_mode = "login"

    def _snack(self, msg: str) -> None:
        dlg = ft.AlertDialog(
            content=ft.Text(msg), actions=[ft.TextButton("OK")],
            actions_alignment=ft.MainAxisAlignment.END)
        dlg.actions[0].on_click = lambda e: self.page.pop_dialog()
        self.page.show_dialog(dlg)

    # ---------------------------------------------------------------- trips --
    def _trips_view(self) -> ft.Control:
        from views.auth import build_login
        if not self.cloud_on:
            return ft.Container(content=ft.Column([
                ft.Text("Trips unavailable offline",
                        size=18, weight=ft.FontWeight.BOLD),
                ft.Text("Add SUPABASE_URL + SUPABASE_ANON_KEY to .env, "
                        "restart, and log in. See SETUP_TRIPS.md.",
                        color=ft.Colors.ON_SURFACE_VARIANT),
            ], tight=True), padding=24)
        if self.user_id is None:
            # Unreachable when cloud is on (app-wide gate), kept as fallback.
            return build_login(on_login=self._do_login,
                               on_go_signup=self._go_signup,
                               error=self.cloud_error)
        if self.open_trip_id:
            return self._trip_detail_view()
        from views.trips import build_trips_list
        return build_trips_list(
            trips=self.trips, totals=self.trip_totals,
            action_needed=self.trip_actions, loading=self.trips_loading,
            error=self.cloud_error, on_open=self._open_trip,
            on_refresh=self._refresh_trips, on_create=self._create_trip_dialog,
            on_join=self._join_code_dialog)

    def _refresh_trips(self, e=None) -> None:
        if not self.cloud_on or not self.user_id:
            return
        self.trips_loading = True
        try:
            self.trips = cloud_trips.list_my_trips()
            self.cloud_error = ""
            totals, actions = {}, {}
            for t in self.trips:
                try:
                    s, _e = cloud_trips.trip_summary(t.id)
                    totals[t.id] = s.total_paise
                    actions[t.id] = cloud_trips.action_needed_count(
                        self.user_id, t.id)
                except Exception:
                    pass
            self.trip_totals, self.trip_actions = totals, actions
        except Exception as exc:
            self.cloud_error = self._net_err(exc)
            self._expired_or_error()
        finally:
            self.trips_loading = False
        if self.tab == 3 and self.open_trip_id is None:
            self.render()

    # ------------------------------------------------------------ trip open --
    def _open_trip(self, trip_id: str) -> None:
        self.open_trip_id, self.trip_view = trip_id, "detail"
        self._load_trip()
        self._start_poll("trip")
        self.render()

    def _trip_back(self) -> None:
        self._stop_poll()
        self.open_trip_id = None
        self._refresh_trips()
        self._start_poll("trips")
        self.render()

    def _load_trip(self) -> None:
        try:
            trip = cloud_trips.get_trip(self.open_trip_id)
            if trip is None:
                self.cloud_error = ("Trip not found — it may have been "
                                    "removed, or you're no longer a member.")
                return
            summary, expenses = cloud_trips.trip_summary(self.open_trip_id)
            members = cloud_trips.list_members(self.open_trip_id)
            settlements = []
            if not trip.is_open:
                try:
                    settlements = cloud_trips.list_settlements(self.open_trip_id)
                except Exception:
                    pass
            my_ids = {m.id for m in members if m.user_id == self.user_id}
            me = next((m for m in members if m.user_id == self.user_id), None)
            self.trip_data = {"trip": trip, "summary": summary,
                              "expenses": expenses, "members": members,
                              "settlements": settlements,
                              "my_member_ids": my_ids,
                              "i_am_admin": bool(me and me.role == "admin"),
                              "preview": False}
            self.cloud_error = ""
        except Exception as exc:
            self.cloud_error = self._net_err(exc)
            self._expired_or_error()

    def _trip_load_failed_view(self) -> ft.Control:
        """Error card shown when a trip can't be loaded (network/removed)."""
        return ft.Container(content=ft.Column([
            ft.Icon(ft.Icons.CLOUD_OFF, size=48, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text("Couldn't load this trip",
                    size=18, weight=ft.FontWeight.BOLD),
            ft.Text(self.cloud_error or "Check your connection and retry.",
                    color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Button("Retry", icon=ft.Icons.REFRESH,
                      on_click=lambda e: self._retry_trip()),
            ft.OutlinedButton("Back to trips",
                              icon=ft.Icons.ARROW_BACK,
                              on_click=lambda e: self._trip_back()),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True,
            spacing=12),
            padding=32, alignment=ft.Alignment.CENTER)

    def _retry_trip(self) -> None:
        self._load_trip()
        self.render()

    def _trip_detail_view(self) -> ft.Control:
        d = self.trip_data
        if not d or d.get("trip") is None or \
                d["trip"].id != self.open_trip_id:
            self._load_trip()
            d = self.trip_data
        if not d or d.get("trip") is None:
            # Never build screens from None (previous crash): show errors.
            return self._trip_load_failed_view()
        if self.trip_view == "settlement":
            from views.settlement_view import build_settlement
            return build_settlement(
                trip=d["trip"], summary=d["summary"],
                settlements=d.get("settlements", []), members=d["members"],
                my_member_ids=d.get("my_member_ids", set()),
                i_am_admin=bool(d.get("i_am_admin", False)),
                preview=bool(d.get("preview", False)),
                error=self.cloud_error, on_mark_paid=self._settle_mark,
                on_confirm=self._settle_confirm, on_reject=self._settle_reject,
                on_back=self._settlement_back)
        from views.trip_detail import build_trip_detail
        my = next((m.id for m in d["members"] if m.user_id == self.user_id), None)
        return build_trip_detail(
            trip=d["trip"], summary=d["summary"], expenses=d["expenses"],
            members=d["members"], my_member_id=my, error=self.cloud_error,
            on_add_expense=self._expense_dialog,
            on_delete_expense=self._delete_expense,
            on_manage_members=self._members_dialog,
            on_end_trip=self._end_trip,
            on_open_settlement=self._open_settlement,
            on_back=self._trip_back)

    # --------------------------------------------------------------- polling --
    def _start_poll(self, what: str) -> None:
        self._stop_poll()
        self._polling = True
        try:
            # run_task takes the coroutine *function* + args (not a coroutine
            # object — passing the object warns "never awaited" and polls never).
            self.page.run_task(self._poll_loop, what)
        except Exception:
            self._polling = False

    def _stop_poll(self) -> None:
        self._polling = False

    async def _poll_loop(self, what: str) -> None:
        while self._polling:
            await asyncio.sleep(5)
            if not self._polling:
                break
            try:
                if what == "trips" and self.tab == 3 and not self.open_trip_id:
                    self._refresh_trips()
                elif what == "trip" and self.open_trip_id:
                    # Refresh the live expense view only — never yank the
                    # settlement screen away while the user is on it.
                    if self.trip_view == "detail":
                        self._load_trip()
                        self.render()
            except Exception:
                pass

    # ------------------------------------------------------------ trip write --
    def _create_trip_dialog(self, e=None) -> None:
        from views.trips import trip_form_dialog

        def submit(f: dict):
            try:
                t = cloud_trips.create_trip(
                    name=f["name"], destination=f.get("destination", ""),
                    description=f.get("description", ""))
                self.page.pop_dialog()
                self._refresh_trips()
                self._open_trip(t.id)
            except ValueError:
                raise  # validation → shown inside the dialog
            except Exception as exc:
                self.cloud_error = self._net_err(exc)
                self.page.pop_dialog()
                self.render()

        dlg, parts = trip_form_dialog(on_submit=submit)
        parts["cancel"].on_click = lambda e: self.page.pop_dialog()
        self.page.show_dialog(dlg)

    def _join_code_dialog(self, e=None) -> None:
        from views.trips import join_code_dialog

        def submit(code: str):
            try:
                tid = cloud_trips.join_with_code(code)
                self.page.pop_dialog()
                self._refresh_trips()
                self._open_trip(tid)
            except ValueError:
                raise  # validation → shown inside the dialog
            except Exception as exc:
                self.cloud_error = self._net_err(exc)
                self.page.pop_dialog()
                self.render()

        dlg = join_code_dialog(on_submit=submit)
        dlg.actions[0].on_click = lambda e: self.page.pop_dialog()
        self.page.show_dialog(dlg)

    def _expense_dialog(self, e=None) -> None:
        from views.trip_detail import expense_form_dialog
        members = self.trip_data.get("members", [])

        def submit(f: dict):
            try:
                cloud_trips.add_expense(
                    trip_id=self.open_trip_id, title=f["title"],
                    amount_paise=f["amount_paise"], category=f["category"],
                    paid_by_member=f["paid_by_member"])
                self.page.pop_dialog()
                self._load_trip()
                self.render()
            except ValueError:
                raise  # validation → shown inside the dialog
            except Exception as exc:
                self.cloud_error = self._net_err(exc)
                self.page.pop_dialog()
                self.render()

        dlg = expense_form_dialog(members=members, on_submit=submit)
        dlg.actions[0].on_click = lambda e: self.page.pop_dialog()
        self.page.show_dialog(dlg)

    def _delete_expense(self, expense_id: str) -> None:
        # One-tap delete is too easy to hit — confirm first (parity with
        # personal entries/categories).
        def confirm(e):
            try:
                cloud_trips.delete_expense(expense_id)
                self._load_trip()
            except Exception as exc:
                self.cloud_error = self._net_err(exc)
            self.page.pop_dialog()
            self.render()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Delete expense?"),
            content=ft.Text("This removes it from everyone's trip totals. "
                            "This cannot be undone."),
            actions=[ft.TextButton("Cancel",
                                   on_click=lambda e: self.page.pop_dialog()),
                     ft.Button("Delete", icon=ft.Icons.DELETE_OUTLINE,
                               bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR,
                               on_click=confirm)],
            actions_alignment=ft.MainAxisAlignment.END, modal=True))

    def _members_dialog(self, e=None) -> None:
        import backend.profiles as profmod
        from backend.money import normalize_phone
        from utils import FIELD_BORDER
        trip = self.trip_data["trip"]
        members = self.trip_data.get("members", [])
        q = ft.TextField(label="Username or phone", border=FIELD_BORDER)
        guest = ft.TextField(label="Guest name (name only)", border=FIELD_BORDER)
        phone = ft.TextField(label="Invite phone (optional)",
                             border=FIELD_BORDER,
                             keyboard_type=ft.KeyboardType.PHONE)
        msg = ft.Text("", size=12)
        rows = ft.Column(
            [ft.Text(f"{m.display_name}  ({m.role})"
                     + (" — guest" if m.is_guest else "")) for m in members],
            tight=True)

        def add_user(e):
            try:
                found = profmod.search_user(q.value or "")
                if not found:
                    msg.value = "No registered user found."
                    msg.update()
                    return
                cloud_trips.add_registered_member(trip.id, found[0])
                self.page.pop_dialog()
                self._load_trip()
                self.render()
            except Exception as exc:
                msg.value = self._net_err(exc)
                msg.update()

        def add_guest(e):
            try:
                cloud_trips.add_guest(trip.id, guest.value or "")
                self.page.pop_dialog()
                self._load_trip()
                self.render()
            except Exception as exc:
                msg.value = self._net_err(exc)
                msg.update()

        def invite(e):
            try:
                res = cloud_trips.invite_phone(trip.id, phone.value or "")
                msg.value = ("Member added directly." if res == "added"
                             else "Invited — auto-joins on sign-up.")
                msg.update()
            except Exception as exc:
                msg.value = self._net_err(exc)
                msg.update()

        dlg = ft.AlertDialog(
            title=ft.Text(f"Members • code {trip.join_code}"),
            content=ft.Column(
                [rows, q, ft.Button("Add user", on_click=add_user),
                 guest, ft.Button("Add guest", on_click=add_guest),
                 phone, ft.Button("Invite phone", on_click=invite), msg],
                tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
            actions=[ft.TextButton(
                "Done", on_click=lambda e: self.page.pop_dialog())],
            modal=True)
        self.page.show_dialog(dlg)

    def _end_trip(self, e=None) -> None:
        def confirm(e):
            try:
                self.trip_data["settlements"] = \
                    cloud_trips.end_trip_and_settle(self.open_trip_id)
                self.page.pop_dialog()
                self._load_trip()
                self.trip_view = "settlement"
            except Exception as exc:
                self.cloud_error = self._net_err(exc)
                self.page.pop_dialog()
            self.render()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("End trip?"),
            content=ft.Text("This locks all expenses and generates the "
                            "settlement. This cannot be undone."),
            actions=[ft.TextButton("Cancel",
                                   on_click=lambda e: self.page.pop_dialog()),
                     ft.Button("End trip", on_click=confirm)],
            actions_alignment=ft.MainAxisAlignment.END, modal=True))

    # ------------------------------------------------------------ settlement --
    def _open_settlement(self, e=None) -> None:
        try:
            trip = self.trip_data.get("trip")
            if trip is not None and trip.is_open:
                # Live preview: who-pays-whom right now, no DB writes.
                _summary, preview = cloud_trips.preview_settlement(
                    self.open_trip_id)
                self.trip_data["settlements"] = preview
                self.trip_data["preview"] = True
            else:
                self.trip_data["settlements"] = cloud_trips.list_settlements(
                    self.open_trip_id)
                self.trip_data["preview"] = False
            self.cloud_error = ""
        except Exception as exc:
            self.cloud_error = self._net_err(exc)
        self.trip_view = "settlement"
        self.render()

    def _settlement_back(self) -> None:
        self.trip_view = "detail"
        self.render()

    def _settle_mark(self, sid: str) -> None:
        self._settle_do(sid, cloud_trips.mark_paid)

    def _settle_confirm(self, sid: str) -> None:
        self._settle_do(sid, cloud_trips.confirm_payment)

    def _settle_reject(self, sid: str) -> None:
        self._settle_do(sid, cloud_trips.reject_payment)

    def _settle_do(self, sid: str, fn) -> None:
        try:
            fn(sid)
            self.trip_data["settlements"] = cloud_trips.list_settlements(
                self.open_trip_id)
            self.cloud_error = ""
        except Exception as exc:
            self.cloud_error = self._net_err(exc)
        self.render()

    # ------------------------------------------------------------------ misc --
    @staticmethod
    def _net_err(exc: Exception) -> str:
        m = str(exc).lower()
        if any(k in m for k in
               ("network", "fetch", "connection", "timeout", "unreachable",
                "name or service", "nodename")):
            return "No internet — check your connection and retry."
        if "row-level security" in m or "policy" in m or "permission denied" in m:
            return ("Permission denied — make sure the latest SQL files ran in "
                    "Supabase (supabase/schema.sql and the migration_*.sql files).")
        return str(exc) or "Something went wrong — retry."


def main(page: ft.Page) -> None:
    TrackMoneyApp(page)


if __name__ == "__main__":
    ft.run(main)
