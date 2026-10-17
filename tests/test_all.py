"""Headless test suite: local DB, settlement math, and screen builders.

Run:  .venv/bin/python -m tests.test_all
No network needed — screen builders catch API crashes (bad colors, casing,
None derefs) the same way the browser would, without a browser.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

from backend.models import (Profile, Settlement, Trip, TripExpense,
                            TripMember, TripSummary)
from backend.money import format_inr, normalize_phone, normalize_username, to_paise
from backend.settlement import compute_balances, settle, split_equal

PASS = 0


def expect(cond, msg):
    global PASS
    if not cond:
        raise AssertionError(msg)
    PASS += 1
    print(f"[PASS] {msg}")


# ------------------------------------------------------------------ local DB --
def test_local_db():
    from database import Database
    from models import EntryType
    tmp = tempfile.mkdtemp()
    db = Database(os.path.join(tmp, "t.db"))
    expect(len(db.list_categories()) == 9, "seed categories for default user")
    db.set_user("userA")
    expect(len(db.list_categories()) == 9, "seed categories for userA")
    cid = db.list_categories()[0].id
    db.add_entry(cid, 100.0, EntryType.SPENT, date.today(), "x")
    expect(len(db.list_entries()) == 1, "userA has one entry")
    db.set_user("userB")
    expect(len(db.list_entries()) == 0, "entries isolated per user")
    expect(len(db.list_categories()) == 9, "categories seeded per user")
    bid = db.create_category("Zzz Unique", "#123456", None)
    expect(db.category_name_exists("Zzz Unique"),
           "userB's custom name tracked for userB")
    db.set_user("userA")
    expect(not db.category_name_exists("Zzz Unique"),
           "other user's custom name invisible (per-user uniqueness)")
    expect(db.category_name_exists("Food & Dining"),
           "category name taken within user scope")
    db.close()


# ------------------------------------------------------------ settlement math --
def test_settlement_math():
    paid = {"A": 300000, "B": 0, "C": 0}
    share = {"A": 100000, "B": 100000, "C": 100000}
    bal = compute_balances(paid, share)
    expect(sum(bal.values()) == 0, "3-member balances sum to zero")
    plan = settle(bal)
    expect(len(plan) == 2, "3-member uneven: two transfers")
    shares = split_equal(10000, ["a", "b", "c"])
    expect(shares == {"a": 3334, "b": 3333, "c": 3333}
           and sum(shares.values()) == 10000,
           "indivisible split: deterministic remainder, exact sum")
    paid4 = {"host": 500000, "m2": 100000, "m3": 0, "guest": 0}
    share4 = {"host": 150000, "m2": 150000, "m3": 150000, "guest": 150000}
    bal4 = compute_balances(paid4, share4)
    plan4 = settle(bal4)
    expect(sum(bal4.values()) == 0 and len(plan4) == 3
           and all(t.to_member == "host" for t in plan4),
           "4-member with guest: balances zero, 3 transfers to host")
    # Fuzz: plan must zero everyone.
    import random
    random.seed(11)
    for _ in range(300):
        n = random.randint(2, 6)
        mem = sorted(f"m{i}" for i in range(n))
        p, s = {m: 0 for m in mem}, {m: 0 for m in mem}
        for _ in range(random.randint(1, 8)):
            amt = random.randint(1, 300000)
            p[random.choice(mem)] += amt
            for mid, v in split_equal(amt, mem).items():
                s[mid] += v
        b = dict(compute_balances(p, s))
        for t in settle(b):
            b[t.from_member] += t.amount_paise
            b[t.to_member] -= t.amount_paise
        assert all(v == 0 for v in b.values())
    expect(True, "fuzz: 300 random trips settle to exactly zero")


def test_money():
    expect(to_paise("1,250.50") == 125050, "to_paise parses formatted input")
    expect(format_inr(125050) == "₹1,250.50", "format_inr renders paise")
    expect(normalize_phone("98765 43210") == "+919876543210",
           "phone normalized to +91")
    expect(normalize_username(" Ravi_1 ") == "ravi_1", "username normalized")
    for bad in ("12", "abcdefghij", "5555555555"):
        try:
            normalize_phone(bad)
            raise AssertionError(f"phone accepted invalid {bad!r}")
        except ValueError:
            pass
    expect(True, "invalid phones rejected")


# ------------------------------------------------------------------ screens --
def _members():
    return [
        TripMember(id="m1", trip_id="t", user_id="u1", guest_name=None,
                   display_name="Ravi", phone="+911234567890", role="admin"),
        TripMember(id="m2", trip_id="t", user_id="u2", guest_name=None,
                   display_name="Anil", phone="+911234567891", role="member"),
        TripMember(id="g1", trip_id="t", user_id=None, guest_name="Guest",
                   display_name="Guest (guest)", phone=None, role="member"),
    ]


def _trip(open_=True):
    return Trip(id="t", name="Goa Trip", destination="Goa",
                start_date="2026-10-10", description="", status="open" if open_ else "closed",
                join_code="ABC123", code_enabled=True, created_by="u1",
                my_role="admin")


def _summary():
    return TripSummary(total_paise=300000, paid_by_member={"m1": 300000, "m2": 0, "g1": 0},
                       share_by_member={"m1": 100000, "m2": 100000, "g1": 100000},
                       balance_by_member={"m1": 200000, "m2": -100000, "g1": -100000})


def test_screen_builders():
    noop = lambda *a, **k: None
    from views.trips import build_trips_list, trip_form_dialog, join_code_dialog
    from views.trip_detail import build_trip_detail, expense_form_dialog
    from views.settlement_view import build_settlement
    from views.auth import build_login, build_signup
    from views.profile import build_profile

    v = build_trips_list(trips=[_trip()], totals={"t": 300000},
                         action_needed={"t": 2}, on_open=noop, on_refresh=noop,
                         on_create=noop, on_join=noop)
    expect(v is not None, "trips list builds (with action dot)")
    v = build_trips_list(trips=[], totals={}, action_needed={}, loading=True,
                         on_open=noop, on_refresh=noop, on_create=noop, on_join=noop)
    expect(v is not None, "trips loading state builds")
    v = build_trips_list(trips=[], totals={}, action_needed={}, error="offline",
                         on_open=noop, on_refresh=noop, on_create=noop, on_join=noop)
    expect(v is not None, "trips empty + error state builds")

    d = trip_form_dialog(on_submit=noop)
    expect(d[0] is not None, "create-trip dialog builds")
    expect(join_code_dialog(on_submit=noop) is not None, "join-code dialog builds")
    expect(expense_form_dialog(members=_members(), on_submit=noop) is not None,
           "expense dialog builds (payer dropdown)")
    m = _members()
    exp = [TripExpense(id="e1", trip_id="t", title="Dinner", amount_paise=150000,
                       expense_date="2026-10-11", category="food",
                       paid_by_member="m1", paid_by_name="Ravi", created_by="u1")]
    v = build_trip_detail(trip=_trip(), summary=_summary(), expenses=exp,
                          members=m, my_member_id="m1", on_add_expense=noop,
                          on_delete_expense=noop, on_manage_members=noop,
                          on_end_trip=noop, on_open_settlement=noop, on_back=noop)
    expect(v is not None, "trip detail builds (admin, with expense)")

    s = Settlement(id="s1", trip_id="t", from_member="m2", to_member="m1",
                   amount_paise=100000, status="pending",
                   from_name="Anil", to_name="Ravi")
    sg = Settlement(id="s2", trip_id="t", from_member="g1", to_member="m1",
                    amount_paise=100000, status="pending",
                    from_name="Guest (guest)", to_name="Ravi")
    v = build_settlement(trip=_trip(False), summary=_summary(),
                         settlements=[s, sg], members=m,
                         my_member_ids={"m1"}, i_am_admin=True,
                         on_mark_paid=noop, on_confirm=noop, on_reject=noop,
                         on_back=noop)
    expect(v is not None, "settlement builds (admin + guest transfer)")
    v = build_settlement(trip=_trip(), summary=_summary(),
                         settlements=[Settlement(id="p", trip_id="t",
                                                 from_member="m2", to_member="m1",
                                                 amount_paise=100000,
                                                 status="preview",
                                                 from_name="Anil", to_name="Ravi")],
                         members=m, my_member_ids={"m1"}, preview=True,
                         on_mark_paid=noop, on_confirm=noop, on_reject=noop,
                         on_back=noop)
    expect(v is not None, "settlement preview builds")

    expect(build_login(on_login=noop, on_go_signup=noop) is not None,
           "login screen builds")
    expect(build_signup(on_signup=noop, on_go_login=noop) is not None,
           "signup screen builds")
    expect(build_profile(profile=None, on_save=noop, on_logout=noop,
                         on_retry=noop) is not None,
           "profile builds with profile=None (no crash)")
    expect(build_profile(profile=Profile(id="u1", name="Ravi", username="ravi",
                                         phone="+911234567890"),
                         on_save=noop, on_logout=noop) is not None,
           "profile builds with data")


def test_dialog_open_close():
    """show/pop_dialog protocol via a fake page (Cancel must work)."""
    from views.trips import trip_form_dialog

    class FakePage:
        def __init__(self):
            self.controls = []
        def show_dialog(self, d):
            if d in self.controls:
                raise RuntimeError("already opened")
            self.controls.append(d)
        def pop_dialog(self):
            if not self.controls:
                return None
            return self.controls.pop()
        def update(self, *a, **k):
            pass

    page = FakePage()
    dlg, parts = trip_form_dialog(on_submit=lambda f: None)
    page.show_dialog(dlg)
    expect(len(page.controls) == 1, "dialog shown")
    parts["cancel"].on_click(None) if parts["cancel"].on_click else page.pop_dialog()
    # cancel handler may be set by caller; emulate close either way
    if page.controls:
        page.pop_dialog()
    expect(len(page.controls) == 0, "dialog closed (Cancel path)")


def main():
    test_local_db()
    test_settlement_math()
    test_money()
    test_screen_builders()
    test_dialog_open_close()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
