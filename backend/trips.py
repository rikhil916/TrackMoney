"""Trip CRUD, members, invites, expenses and settlement RPC wrappers.

Every function here talks to Supabase; screens import only this module
(plus money/models), never supabase directly.
"""

from __future__ import annotations

import random
import string
from datetime import date

from backend import settlement as calc
from backend.config import get_client
from backend.models import (
    Profile, Settlement, Trip, TripExpense, TripMember, TripSummary,
)
from backend.money import check_trip_name, normalize_phone

_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no confusables
EXPENSE_CATS = ("food", "travel", "stay", "shopping", "activity", "other")


def _c():
    return get_client()


def _my_uid() -> str:
    from backend.auth import require_uid
    return require_uid()


def _new_code() -> str:
    return "".join(random.choice(_CODE_ALPHABET) for _ in range(6))


# ------------------------------------------------------------ trips --
def create_trip(*, name: str, destination: str = "", start_date=None,
                description: str = "") -> Trip:
    c = _c()
    uid = _my_uid()
    name = check_trip_name(name)
    prof = c.table("profiles").select("name").eq("id", uid).execute().data
    my_name = prof[0]["name"] if prof else "Admin"
    for _ in range(5):
        code = _new_code()
        try:
            row = c.table("trips").insert({
                "name": name, "destination": (destination or "").strip() or None,
                "start_date": str(start_date or date.today()),
                "description": (description or "").strip(),
                "join_code": code, "created_by": uid,
            }).execute().data[0]
            break
        except Exception as exc:
            if "duplicate" not in str(exc).lower():
                raise
    else:
        raise RuntimeError("could not generate a join code — retry")
    c.table("trip_members").insert({
        "trip_id": row["id"], "user_id": uid,
        "display_name": my_name, "role": "admin",
    }).execute()
    return _row_to_trip(row, my_role="admin")


def list_my_trips() -> list[Trip]:
    c = _c()
    uid = _my_uid()
    mems = c.table("trip_members").select("trip_id,role").eq(
        "user_id", uid).execute().data
    if not mems:
        return []
    roles = {m["trip_id"]: m["role"] for m in mems}
    rows = c.table("trips").select("*").in_(
        "id", list(roles)).order("created_at", desc=True).execute().data
    return [_row_to_trip(r, my_role=roles.get(r["id"], "member")) for r in rows]


def get_trip(trip_id: str) -> Trip | None:
    c = _c()
    rows = c.table("trips").select("*").eq("id", trip_id).execute().data
    if not rows:
        return None
    mems = c.table("trip_members").select("role").eq(
        "trip_id", trip_id).eq("user_id", _my_uid()).execute().data
    return _row_to_trip(rows[0], my_role=mems[0]["role"] if mems else "member")


def set_code_enabled(trip_id: str, enabled: bool) -> None:
    _c().table("trips").update({"code_enabled": enabled}).eq("id", trip_id).execute()


def _row_to_trip(r: dict, my_role: str = "member") -> Trip:
    return Trip(id=r["id"], name=r["name"], destination=r.get("destination"),
                start_date=str(r.get("start_date", "")),
                description=r.get("description") or "", status=r.get("status", "open"),
                join_code=r.get("join_code", ""), code_enabled=bool(r.get("code_enabled")),
                created_by=r.get("created_by", ""), my_role=my_role)


# ---------------------------------------------------------- members --
def list_members(trip_id: str) -> list[TripMember]:
    rows = _c().table("trip_members").select("*").eq(
        "trip_id", trip_id).order("created_at").execute().data
    return [TripMember(id=r["id"], trip_id=r["trip_id"], user_id=r.get("user_id"),
                       guest_name=r.get("guest_name"),
                       display_name=r.get("display_name", "?"),
                       phone=r.get("phone"), role=r.get("role", "member"))
            for r in rows]


def _friendly_dup(exc: Exception, msg: str) -> Exception:
    m = str(exc).lower()
    if "duplicate" in m or "unique" in m or "23505" in m:
        return ValueError(msg)
    return exc


def add_registered_member(trip_id: str, profile: Profile) -> None:
    try:
        _c().table("trip_members").insert({
            "trip_id": trip_id, "user_id": profile.id,
            "display_name": profile.name, "phone": profile.phone,
            "role": "member",
        }).execute()
    except Exception as exc:
        raise _friendly_dup(exc, f"{profile.name} is already in this trip") from exc


def add_guest(trip_id: str, guest_name: str) -> TripMember:
    guest_name = (guest_name or "").strip()
    if not guest_name:
        raise ValueError("guest name cannot be empty")
    r = _c().table("trip_members").insert({
        "trip_id": trip_id, "user_id": None,
        "guest_name": guest_name, "display_name": guest_name + " (guest)",
        "role": "member",
    }).execute().data[0]
    return TripMember(id=r["id"], trip_id=trip_id, user_id=None,
                      guest_name=guest_name, display_name=r["display_name"],
                      phone=None, role="member")


def remove_member(trip_id: str, member_id: str) -> None:
    _c().table("trip_members").delete().eq("id", member_id).execute()


def invite_phone(trip_id: str, raw_phone: str) -> str:
    """Pending invite by phone; returns 'added' or 'invited'."""
    c = _c()
    ph = normalize_phone(raw_phone)
    rows = c.table("profiles").select("id,name").eq("phone", ph).execute().data
    if rows:
        try:
            c.table("trip_members").insert({
                "trip_id": trip_id, "user_id": rows[0]["id"],
                "display_name": rows[0]["name"], "phone": ph, "role": "member",
            }).execute()
        except Exception as exc:
            raise _friendly_dup(
                exc, f"{rows[0]['name']} is already in this trip") from exc
        return "added"
    pending = c.table("trip_invites").select("id").eq("trip_id", trip_id).eq(
        "phone", ph).eq("status", "pending").execute().data
    if pending:
        raise ValueError("that number is already invited to this trip")
    c.table("trip_invites").insert(
        {"trip_id": trip_id, "phone": ph, "invited_by": _my_uid()}).execute()
    return "invited"


def join_with_code(code: str) -> str:
    """Join via 6-char code. Returns the trip id. Bad codes raise ValueError
    (so the dialog can show the message inline)."""
    code = (code or "").strip().upper()
    try:
        r = _c().rpc("join_trip_by_code", {"p_code": code}).execute()
    except Exception as exc:
        if "invalid or disabled join code" in str(exc).lower():
            raise ValueError("that code is invalid or no longer enabled") from exc
        raise
    return r.data


def lookup_code(code: str) -> dict | None:
    rows = _c().rpc("lookup_trip_by_code",
                    {"p_code": (code or '').strip().upper()}).execute().data
    return rows[0] if rows else None


# ---------------------------------------------------------- expenses --
def list_expenses(trip_id: str) -> tuple[list[TripExpense], dict[str, list[tuple[str, int]]]]:
    """Returns (expenses, splits_by_expense {expense_id: [(member_id, paise)]}).

    paid_by names are resolved from trip members (one extra query).
    """
    c = _c()
    exp_rows = c.table("trip_expenses").select("*").eq(
        "trip_id", trip_id).order("expense_date", desc=True).execute().data
    members = {m.id: m.display_name for m in list_members(trip_id)}
    expenses = [TripExpense(
        id=r["id"], trip_id=trip_id, title=r["title"],
        amount_paise=int(r["amount_paise"]), expense_date=str(r["expense_date"]),
        category=r.get("category", "other"), paid_by_member=r["paid_by_member"],
        paid_by_name=members.get(r["paid_by_member"], "?"),
        created_by=r.get("created_by", "")) for r in exp_rows]
    splits: dict[str, list[tuple[str, int]]] = {}
    if exp_rows:
        ids = [r["id"] for r in exp_rows]
        for s in c.table("expense_splits").select("*").in_(
                "expense_id", ids).execute().data:
            splits.setdefault(s["expense_id"], []).append(
                (s["member_id"], int(s["share_paise"])))
    return expenses, splits


def add_expense(*, trip_id: str, title: str, amount_paise: int, expense_date=None,
                category: str = "other", paid_by_member: str) -> str:
    """Record who paid. The split is NOT chosen here — at settlement time the
    total is divided equally among ALL members (guests included).

    Equal placeholder splits are still written so the DB's split-sum guard
    stays satisfied; trip_summary() recomputes shares fresh from the final
    member list, so late joiners are included fairly.
    """
    title = (title or "").strip()
    if not title:
        raise ValueError("expense needs a title")
    if amount_paise <= 0:
        raise ValueError("amount must be positive")
    if category not in EXPENSE_CATS:
        raise ValueError("unknown category")
    c = _c()
    members = list_members(trip_id)
    if not members:
        raise ValueError("trip has no members yet")
    if paid_by_member not in {m.id for m in members}:
        raise ValueError("payer must be a trip member")
    row = c.table("trip_expenses").insert({
        "trip_id": trip_id, "title": title, "amount_paise": amount_paise,
        "expense_date": str(expense_date or date.today()), "category": category,
        "paid_by_member": paid_by_member, "created_by": _my_uid(),
    }).execute().data[0]
    shares = calc.split_equal(
        amount_paise, [m.id for m in members])
    c.table("expense_splits").insert([
        {"expense_id": row["id"], "member_id": mid, "share_paise": amt}
        for mid, amt in shares.items()
    ]).execute()
    return row["id"]


def delete_expense(expense_id: str) -> None:
    _c().table("trip_expenses").delete().eq("id", expense_id).execute()


def trip_summary(trip_id: str) -> tuple[TripSummary, list[TripExpense]]:
    """Totals with the FINAL split: every expense divided equally among ALL
    current members (late joiners included, guests included).

    Stored expense_splits are only a DB-consistency placeholder; shares here
    are recomputed fresh so the settlement matches the end-of-trip roster.
    """
    members = list_members(trip_id)
    expenses, _splits = list_expenses(trip_id)
    member_ids = sorted(m.id for m in members)
    paid: dict[str, int] = {}
    share: dict[str, int] = {}
    for e in expenses:
        paid[e.paid_by_member] = paid.get(e.paid_by_member, 0) + e.amount_paise
        if member_ids:
            for mid, amt in calc.split_equal(
                    e.amount_paise, member_ids).items():
                share[mid] = share.get(mid, 0) + amt
    # Members with no expenses still owe their share.
    for mid in member_ids:
        paid.setdefault(mid, 0)
        share.setdefault(mid, 0)
    balances = calc.compute_balances(paid, share) if expenses else {}
    total = sum(e.amount_paise for e in expenses)
    return TripSummary(total_paise=total, paid_by_member=paid,
                       share_by_member=share,
                       balance_by_member=balances), expenses


def preview_settlement(trip_id: str) -> tuple[TripSummary, list]:
    """Local who-pays-whom preview for an OPEN trip (no DB writes).

    Returns (summary, [Settlement(...)] with status 'preview').
    """
    summary, _exp = trip_summary(trip_id)
    assert sum(summary.balance_by_member.values()) == 0, \
        "preview balances must sum to zero"
    plan = calc.settle(summary.balance_by_member)
    members = {m.id: m.display_name for m in list_members(trip_id)}
    out = [Settlement(id=f"preview-{i}", trip_id=trip_id,
                      from_member=t.from_member, to_member=t.to_member,
                      amount_paise=t.amount_paise, status="preview",
                      from_name=members.get(t.from_member, "?"),
                      to_name=members.get(t.to_member, "?"))
           for i, t in enumerate(plan)]
    return summary, out


# -------------------------------------------------------- settlement --
def end_trip_and_settle(trip_id: str) -> list[Settlement]:
    """Admin-only: lock the trip and record the settlement plan atomically.

    Calls end_trip() (locks expenses) then record_settlements() with the
    greedy plan computed locally. Returns the stored settlement rows.
    """
    c = _c()
    summary, _exp = trip_summary(trip_id)
    assert sum(summary.balance_by_member.values()) == 0, \
        "settlement balances must sum to zero"
    plan = calc.settle(summary.balance_by_member)
    # member uuids needed for the RPC payload (from_/to_ are member ids).
    c.rpc("end_trip", {"p_trip": trip_id}).execute()
    payload = [{"from_member": t.from_member, "to_member": t.to_member,
                "amount_paise": t.amount_paise} for t in plan]
    c.rpc("record_settlements", {"p_trip": trip_id, "p_items": payload}).execute()
    return list_settlements(trip_id)


def list_settlements(trip_id: str) -> list[Settlement]:
    rows = _c().table("settlements").select("*").eq(
        "trip_id", trip_id).order("created_at").execute().data
    members = {m.id: m.display_name for m in list_members(trip_id)}
    return [Settlement(id=r["id"], trip_id=trip_id, from_member=r["from_member"],
                       to_member=r["to_member"], amount_paise=int(r["amount_paise"]),
                       status=r["status"],
                       from_name=members.get(r["from_member"], "?"),
                       to_name=members.get(r["to_member"], "?")) for r in rows]


def mark_paid(settlement_id: str) -> None:
    _c().rpc("mark_settlement_paid", {"p_id": settlement_id}).execute()


def confirm_payment(settlement_id: str) -> None:
    _c().rpc("confirm_settlement", {"p_id": settlement_id}).execute()


def reject_payment(settlement_id: str) -> None:
    _c().rpc("reject_settlement", {"p_id": settlement_id}).execute()


def action_needed_count(user_id: str, trip_id: str) -> int:
    """Settlements where this user must act (payer: mark paid;
    receiver: confirm/reject). Guests have no login, so as TRIP ADMIN you
    act for guest-side transfers (mirrors the RPC rules)."""
    try:
        members = list_members(trip_id)
    except Exception:
        return 0
    mine = [m for m in members if m.user_id == user_id]
    if not mine:
        return 0
    my_ids = {m.id for m in mine}
    i_am_admin = mine[0].role == "admin"
    guest_ids = {m.id for m in members if m.user_id is None}
    try:
        st = list_settlements(trip_id)
    except Exception:
        return 0
    n = 0
    for s in st:
        can_pay = s.from_member in my_ids or (i_am_admin and s.from_member in guest_ids)
        can_recv = s.to_member in my_ids or (i_am_admin and s.to_member in guest_ids)
        if s.status == "pending" and can_pay:
            n += 1  # payer must mark paid
        elif s.status == "paid" and can_recv:
            n += 1  # receiver (or admin for guest) must confirm/reject
    return n
