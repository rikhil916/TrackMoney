"""Pure settlement math (no network, no UI).

Convention: balances are INTEGER paise, paid - share.
Positive = creditor (is owed), negative = debtor (owes).
Greedy matching: largest debtor pays largest creditor, minimizing transfers.
Uneven division remainder goes to the earliest members (stable order), so the
balances always sum to exactly zero.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transfer:
    from_member: str
    to_member: str
    amount_paise: int


def compute_balances(
    paid: dict[str, int], share: dict[str, int]
) -> dict[str, int]:
    """paid/share in paise -> balance per member. Always sums to zero."""
    members = sorted(set(paid) | set(share))
    total_paid = sum(paid.get(m, 0) for m in members)
    total_share = sum(share.get(m, 0) for m in members)
    assert total_paid == total_share, (
        f"paid ({total_paid}) and share ({total_share}) must match")
    return {m: paid.get(m, 0) - share.get(m, 0) for m in members}


def split_equal(total_paise: int, member_ids: list[str]) -> dict[str, int]:
    """Split total paise equally; remainder paise go to earliest members."""
    if not member_ids:
        raise ValueError("split needs at least one member")
    if total_paise <= 0:
        raise ValueError("total must be positive")
    ids = sorted(member_ids)
    base, rem = divmod(total_paise, len(ids))
    out = {m: base for m in ids}
    for m in ids[:rem]:
        out[m] += 1
    assert sum(out.values()) == total_paise
    return out


def settle(balances: dict[str, int]) -> list[Transfer]:
    """Greedy min-transfer settlement from a balance map (paise)."""
    debtors = sorted(
        ((m, -b) for m, b in balances.items() if b < 0),
        key=lambda x: -x[1])
    creditors = sorted(
        ((m, b) for m, b in balances.items() if b > 0),
        key=lambda x: -x[1])
    out: list[Transfer] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        dm, d_amt = debtors[i]
        cm, c_amt = creditors[j]
        x = min(d_amt, c_amt)
        out.append(Transfer(from_member=dm, to_member=cm, amount_paise=x))
        d_amt -= x
        c_amt -= x
        if d_amt == 0:
            i += 1
        else:
            debtors[i] = (dm, d_amt)
        if c_amt == 0:
            j += 1
        else:
            creditors[j] = (cm, c_amt)
    return out


def summarize_expenses(
    expenses: list[tuple[str, int]],
    splits: list[tuple[str, str, int]],
) -> tuple[dict[str, int], dict[str, int]]:
    """Aggregate (paid_by, amount) + (expense, member, share) rows.

    Returns (paid_by_member, share_by_member) in paise.
    """
    paid: dict[str, int] = {}
    share: dict[str, int] = {}
    for member_id, amount in expenses:
        paid[member_id] = paid.get(member_id, 0) + amount
    for _exp, member_id, amount in splits:
        share[member_id] = share.get(member_id, 0) + amount
    return paid, share
