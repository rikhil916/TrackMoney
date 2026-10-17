"""Settlement screen: plan, progress, per-user actions, payment verification."""

from __future__ import annotations

import flet as ft
from backend.money import format_inr
from backend.models import Settlement, Trip, TripMember, TripSummary

STATUS_COLOR = {"pending": ft.Colors.ORANGE, "paid": ft.Colors.BLUE,
                "confirmed": ft.Colors.GREEN, "preview": ft.Colors.TEAL}
STATUS_LABEL = {"pending": "Pending", "paid": "Marked paid",
                "confirmed": "Confirmed", "preview": "Preview"}


def _chip(status: str) -> ft.Chip:
    return ft.Chip(label=ft.Text(STATUS_LABEL.get(status, status), size=12),
                   bgcolor=STATUS_COLOR.get(status, ft.Colors.SURFACE_CONTAINER_HIGHEST))


def _fair_share_line(summary: TripSummary, members: list[TripMember]) -> str:
    """Exact fair-share text (no floor-division rounding error).

    Shares can differ by 1 paise when the total doesn't divide evenly, so a
    single floored number would disagree with the per-member rows below.
    """
    if not members:
        return "No members"
    vals = [summary.share_by_member.get(m.id, 0) for m in members]
    if min(vals) == max(vals):
        return f"Fair share each  {format_inr(vals[0])}  (÷ {len(members)})"
    return (f"Fair share each  {format_inr(min(vals))}–{format_inr(max(vals))} "
            f"(÷ {len(members)}, 1-paise rounding)")


def build_settlement(*, trip: Trip, summary: TripSummary,
                     settlements: list[Settlement], members: list[TripMember],
                     my_member_ids: set[str], i_am_admin=False,
                     preview=False, error="",
                     on_mark_paid, on_confirm, on_reject,
                     on_back) -> ft.Control:
    member_by_id = {m.id: m for m in members}
    total = summary.total_paise
    confirmed = sum(s.amount_paise for s in settlements if s.is_confirmed)
    progress = (confirmed / sum(s.amount_paise for s in settlements)
                if settlements else 1.0)
    fully = settlements and all(s.is_confirmed for s in settlements)

    head: list[ft.Control] = [
        ft.Row([ft.IconButton(ft.Icons.ARROW_BACK,
                              on_click=lambda e: on_back()),
                ft.Text("Settlement" + (" (preview)" if preview else ""),
                        size=20, weight=ft.FontWeight.BOLD, expand=True)]),
        ft.Card(content=ft.Container(content=ft.Column([
            ft.Text(f"Total trip cost  {format_inr(total)}",
                    weight=ft.FontWeight.BOLD),
            ft.Text(_fair_share_line(summary, members),
                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            # Preview has no payments yet — skip the 0% progress bar.
            *([ft.ProgressBar(value=progress)] if not preview else []),
            ft.Text("Live preview — final amounts are set when the admin "
                    "ends the trip." if preview else
                    ("Fully settled 🎉" if fully else
                     f"{format_inr(confirmed)} of "
                     f"{format_inr(sum(s.amount_paise for s in settlements))} confirmed"),
                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ], tight=True, spacing=6), padding=16)),
    ]
    if error:
        head.append(ft.Text(error, color=ft.Colors.ERROR))

    # Fair-share table.
    rows = [ft.Text("Fair shares", weight=ft.FontWeight.BOLD)]
    for m in members:
        rows.append(ft.ListTile(
            leading=ft.CircleAvatar(
                content=ft.Text(m.display_name[:1].upper())),
            title=ft.Text(m.display_name),
            subtitle=ft.Text(
                f"paid {format_inr(summary.paid_by_member.get(m.id, 0))}  •  "
                f"share {format_inr(summary.share_by_member.get(m.id, 0))}"),
            trailing=ft.Text(
                format_inr(summary.balance_by_member.get(m.id, 0)),
                weight=ft.FontWeight.BOLD),
            dense=True))
    head.extend(rows)

    # Transfers with action buttons.
    head.append(ft.Text("Who pays whom", weight=ft.FontWeight.BOLD))
    if not settlements:
        head.append(ft.Text("Nothing to settle — everyone paid their share.",
                            color=ft.Colors.ON_SURFACE_VARIANT))
    for s in settlements:
        # Guests can't log in, so as trip admin you act for their side
        # (matches the mark/confirm/reject RPC rules).
        from_member = member_by_id.get(s.from_member)
        to_member = member_by_id.get(s.to_member)
        from_guest = from_member is not None and from_member.is_guest
        to_guest = to_member is not None and to_member.is_guest
        i_pay = s.from_member in my_member_ids or (i_am_admin and from_guest)
        i_receive = s.to_member in my_member_ids or (i_am_admin and to_guest)
        needs_me = ((s.is_pending and i_pay) or (s.is_paid and i_receive))
        actions: list[ft.Control] = []
        if s.is_pending and i_pay:
            actions.append(ft.Button(
                "Mark as paid", icon=ft.Icons.CHECK,
                on_click=lambda e, sid=s.id: on_mark_paid(sid)))
        if s.is_paid and i_receive:
            actions.append(ft.Row([
                ft.Button("Confirm", icon=ft.Icons.VERIFIED,
                          on_click=lambda e, sid=s.id: on_confirm(sid)),
                ft.TextButton("Reject",
                              on_click=lambda e, sid=s.id: on_reject(sid)),
            ], tight=True))
        card_color = (ft.Colors.PRIMARY_CONTAINER if needs_me else None)
        head.append(ft.Card(content=ft.Container(content=ft.Column([
            ft.Row([
                ft.Text(f"{s.from_name} pays {s.to_name}",
                        weight=ft.FontWeight.BOLD, expand=True),
                _chip(s.status),
            ]),
            ft.Text(format_inr(s.amount_paise), size=20,
                    weight=ft.FontWeight.BOLD),
            ft.Text("⚡ Your action needed",
                    color=ft.Colors.PRIMARY,
                    weight=ft.FontWeight.BOLD) if needs_me else ft.Container(),
            *actions,
        ], tight=True, spacing=6),
            bgcolor=card_color, padding=14,
            border_radius=12)))

    return ft.Container(content=ft.Column(head, spacing=8, tight=True),
                        padding=12)
