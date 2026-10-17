"""Unit tests for the pure settlement math (paise integers, no network)."""

from backend.settlement import (
    Transfer, compute_balances, settle, split_equal, summarize_expenses,
)
from backend.money import format_inr, to_paise


def test_three_members_uneven():
    # A paid 3000, B paid 0, C paid 0; shared equally (1000 each).
    paid = {"A": 300000, "B": 0, "C": 0}
    share = {"A": 100000, "B": 100000, "C": 100000}
    bal = compute_balances(paid, share)
    assert sum(bal.values()) == 0
    plan = settle(bal)
    assert len(plan) == 2
    assert all(t.to_member == "A" and t.amount_paise == 100000 for t in plan)


def test_four_members_with_guest():
    # Host + guest: guest never pays, only absorbs share.
    paid = {"host": 500000, "m2": 100000, "m3": 0, "guest": 0}
    share = {"host": 150000, "m2": 150000, "m3": 150000, "guest": 150000}
    bal = compute_balances(paid, share)
    assert sum(bal.values()) == 0
    plan = settle(bal)
    # Creditors: host (+350000). Debtors: m2 (-50000), m3, guest (-150000 each).
    assert sum(t.amount_paise for t in plan) == 350000
    assert all(t.to_member == "host" for t in plan)
    assert len(plan) == 3


def test_uneven_division_remainder():
    # ₹100 split 3 ways = 3334/3333/3333 paise; remainder is deterministic.
    shares = split_equal(10000, ["a", "b", "c"])
    assert sum(shares.values()) == 10000
    assert shares == {"a": 3334, "b": 3333, "c": 3333}
    # Single paise also splits without loss.
    assert sum(split_equal(1, ["x", "y"]).values()) == 1


def test_greedy_minimizes_transfers():
    # Classic: one creditor, three debtors -> exactly 3 transfers.
    bal = {"rich": 30000, "p1": -10000, "p2": -10000, "p3": -10000}
    plan = settle(bal)
    assert len(plan) == 3
    # Chain settlement (A->B->C) collapses: A pays C directly.
    bal2 = {"A": -5000, "B": 0, "C": 5000}
    plan2 = settle(bal2)
    assert plan2 == [Transfer(from_member="A", to_member="C", amount_paise=5000)]


def test_summarize_and_format():
    paid, share = summarize_expenses(
        [("m1", 20000), ("m2", 10000)],
        [("e1", "m1", 15000), ("e1", "m2", 15000)],
    )
    assert paid == {"m1": 20000, "m2": 10000}
    assert share == {"m1": 15000, "m2": 15000}
    bal = compute_balances(paid, share)
    assert bal == {"m1": 5000, "m2": -5000}
    assert format_inr(125000) == "₹1,250.00"
    assert to_paise("1,250.50") == 125050
