"""Trip detail: expenses, totals, per-member contributions, members.

Same data for every member (single Supabase source of truth).
"""

from __future__ import annotations

import flet as ft
from backend.money import format_inr
from backend.models import Trip, TripExpense, TripMember, TripSummary

CAT_ICON = {"food": ft.Icons.RESTAURANT, "travel": ft.Icons.FLIGHT,
            "stay": ft.Icons.HOTEL, "shopping": ft.Icons.SHOPPING_BAG,
            "activity": ft.Icons.HIKING, "other": ft.Icons.RECEIPT}


def build_trip_detail(*, trip: Trip, summary: TripSummary,
                      expenses: list[TripExpense], members: list[TripMember],
                      my_member_id: str | None, error="",
                      on_add_expense, on_delete_expense, on_manage_members,
                      on_end_trip, on_open_settlement, on_back) -> ft.Control:
    names = {m.id: m.display_name for m in members}
    head: list[ft.Control] = [
        ft.Row([
            ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: on_back()),
            ft.Text(trip.name, size=20, weight=ft.FontWeight.BOLD, expand=True),
            ft.Chip(label=ft.Text("Open" if trip.is_open else "Locked"),
                    bgcolor=ft.Colors.PRIMARY_CONTAINER if trip.is_open
                    else ft.Colors.SURFACE_CONTAINER_HIGHEST),
        ]),
        ft.Text(f"Code: {trip.join_code}" +
                ("" if trip.code_enabled else " (disabled)") +
                (f"  •  {trip.destination}" if trip.destination else ""),
                color=ft.Colors.ON_SURFACE_VARIANT, size=12),
        ft.Card(content=ft.Container(content=ft.Row([
            ft.Column([ft.Text("Total spent", size=12,
                               color=ft.Colors.ON_SURFACE_VARIANT),
                       ft.Text(format_inr(summary.total_paise), size=20,
                               weight=ft.FontWeight.BOLD)]),
            ft.Column([ft.Text("Expenses", size=12,
                               color=ft.Colors.ON_SURFACE_VARIANT),
                       ft.Text(str(len(expenses)), size=20,
                               weight=ft.FontWeight.BOLD)],
                      horizontal_alignment=ft.CrossAxisAlignment.END),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=16)),
    ]
    if error:
        head.append(ft.Text(error, color=ft.Colors.ERROR))

    # Contributions (identical for all members).
    contrib = [ft.Text("Contributions", weight=ft.FontWeight.BOLD)]
    for m in members:
        paid = summary.paid_by_member.get(m.id, 0)
        share = summary.share_by_member.get(m.id, 0)
        bal = summary.balance_by_member.get(m.id, 0)
        color = (ft.Colors.GREEN if bal > 0 else
                 ft.Colors.ERROR if bal < 0 else ft.Colors.ON_SURFACE_VARIANT)
        contrib.append(ft.ListTile(
            leading=ft.CircleAvatar(
                content=ft.Text(m.display_name[:1].upper()),
                bgcolor=ft.Colors.PRIMARY_CONTAINER if m.id == my_member_id else None),
            title=ft.Text(m.display_name + (" (guest)" if m.is_guest else "")
                          + (" (admin)" if m.role == "admin" else "")),
            subtitle=ft.Text(f"paid {format_inr(paid)}  •  share {format_inr(share)}"),
            trailing=ft.Text(format_inr(bal), color=color,
                             weight=ft.FontWeight.BOLD),
            dense=True,
        ))

    # Expense list.
    exp_cards: list[ft.Control] = [ft.Row([
        ft.Text("Expenses", weight=ft.FontWeight.BOLD, expand=True),
        ft.Button("Settlement", icon=ft.Icons.ACCOUNT_BALANCE,
                  on_click=lambda e: on_open_settlement()),
    ])]
    if not expenses:
        exp_cards.append(ft.Text("No expenses yet — add the first one below.",
                                 color=ft.Colors.ON_SURFACE_VARIANT))
    for ex in expenses:
        can_edit = trip.is_open and (
            ex.created_by == "" or True)  # server enforces author-or-admin
        exp_cards.append(ft.Card(content=ft.ListTile(
            leading=ft.Icon(CAT_ICON.get(ex.category, ft.Icons.RECEIPT)),
            title=ft.Text(f"{ex.paid_by_name} paid {format_inr(ex.amount_paise)}"),
            subtitle=ft.Text(f"{ex.title}  •  {ex.expense_date}"),
            trailing=(ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Delete",
                                    on_click=lambda e, eid=ex.id:
                                    on_delete_expense(eid))
                      if can_edit else None),
            dense=True,
        )))

    # Admin row.
    admin_row: list[ft.Control] = []
    if trip.my_role == "admin":
        admin_row.append(ft.Row([
            ft.OutlinedButton("Members", icon=ft.Icons.GROUP,
                              on_click=lambda e: on_manage_members()),
            ft.OutlinedButton("End trip", icon=ft.Icons.LOCK,
                              on_click=lambda e: on_end_trip(),
                              disabled=not trip.is_open),
        ], alignment=ft.MainAxisAlignment.CENTER))

    if trip.is_open:
        admin_row.append(ft.Button("Add expense", icon=ft.Icons.ADD,
                                   on_click=lambda e: on_add_expense()))

    return ft.Container(content=ft.Column(
        [*head, *contrib, *exp_cards, *admin_row], spacing=8, tight=True),
        padding=12)


def expense_form_dialog(*, members: list[TripMember], on_submit) -> ft.AlertDialog:
    """Record one payment: title, amount, category, who paid.

    No split controls — the total is divided equally among ALL members
    (guests included) when the settlement is calculated after the trip.
    """
    from utils import FIELD_BORDER
    from backend.money import to_paise
    from backend.trips import EXPENSE_CATS
    title = ft.TextField(label="Title (e.g. Dinner)", border=FIELD_BORDER)
    amount = ft.TextField(label="Amount ₹", border=FIELD_BORDER,
                          keyboard_type=ft.KeyboardType.NUMBER)
    payer_opts = [ft.dropdown.Option(key=m.id, text=m.display_name)
                  for m in members]
    # Flet 1.0 Dropdown has no on_change — selection must be captured via
    # on_select, otherwise payer.value stays stale and the expense is
    # attributed to the wrong member (corrupting settlement math).
    state = {"category": "food",
             "payer": payer_opts[0].key if payer_opts else None}

    def on_cat_select(e):
        state["category"] = (e.control.value or "food")

    def on_payer_select(e):
        state["payer"] = e.control.value

    cat = ft.Dropdown(label="Category", border=FIELD_BORDER,
                      options=[ft.dropdown.Option(c) for c in EXPENSE_CATS],
                      value="food", on_select=on_cat_select)
    payer = ft.Dropdown(label="Who paid", border=FIELD_BORDER,
                        options=payer_opts,
                        value=state["payer"], on_select=on_payer_select)
    err = ft.Text("", color=ft.Colors.ERROR)

    def submit(e):
        try:
            if not (title.value or "").strip():
                raise ValueError("expense needs a title")
            total = to_paise(amount.value or "0")
            if not state["payer"]:
                raise ValueError("pick who paid")
            on_submit({"title": title.value.strip(), "amount_paise": total,
                       "category": state["category"],
                       "paid_by_member": state["payer"]})
        except ValueError as exc:
            err.value = str(exc)
            err.update()

    return ft.AlertDialog(
        title=ft.Text("Add expense"),
        content=ft.Column(
            [title, amount, cat, payer,
             ft.Text(f"Split equally among all {len(members)} member(s) "
                     "at settlement — nothing to choose now.",
                     size=12, color=ft.Colors.ON_SURFACE_VARIANT),
             err],
            tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
        actions=[ft.TextButton("Cancel"), ft.Button("Save", on_click=submit)],
        actions_alignment=ft.MainAxisAlignment.END, modal=True)
