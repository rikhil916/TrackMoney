"""Typed models for the cloud layer (trips, members, expenses, settlements)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    username: str
    phone: str


@dataclass(frozen=True)
class Trip:
    id: str
    name: str
    destination: str | None
    start_date: str
    description: str
    status: str  # open | closed
    join_code: str
    code_enabled: bool
    created_by: str
    my_role: str = "member"

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True)
class TripMember:
    id: str
    trip_id: str
    user_id: str | None
    guest_name: str | None
    display_name: str
    phone: str | None
    role: str

    @property
    def is_guest(self) -> bool:
        return self.user_id is None


@dataclass(frozen=True)
class TripExpense:
    id: str
    trip_id: str
    title: str
    amount_paise: int
    expense_date: str
    category: str
    paid_by_member: str
    paid_by_name: str = ""
    created_by: str = ""


@dataclass(frozen=True)
class ExpenseSplit:
    expense_id: str
    member_id: str
    share_paise: int


@dataclass(frozen=True)
class Settlement:
    id: str
    trip_id: str
    from_member: str
    to_member: str
    amount_paise: int
    status: str  # pending | paid | confirmed
    from_name: str = ""
    to_name: str = ""

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def is_paid(self) -> bool:
        return self.status == "paid"

    @property
    def is_confirmed(self) -> bool:
        return self.status == "confirmed"


@dataclass
class TripSummary:
    total_paise: int = 0
    paid_by_member: dict[str, int] = field(default_factory=dict)  # member_id -> paise
    share_by_member: dict[str, int] = field(default_factory=dict)
    balance_by_member: dict[str, int] = field(default_factory=dict)  # paid - share

    @property
    def is_empty(self) -> bool:
        return self.total_paise == 0
