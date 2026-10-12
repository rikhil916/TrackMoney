"""Domain models for TrackMoney.

Pure dataclasses + enums. This module has no Flet or SQLite imports so the
data layer stays independent from the UI and can be reused (tests, future
sync, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class EntryType(str, Enum):
    """Whether an entry represents money going out or money kept."""

    SPENT = "spent"
    SAVED = "saved"

    @property
    def label(self) -> str:
        """Human-readable label for buttons/legends."""
        return "Spent" if self is EntryType.SPENT else "Saved"


@dataclass(frozen=True)
class Category:
    """A user-defined spending/saving category."""

    id: int
    name: str
    color: str  # hex string, e.g. "#E85D3F"
    icon: str | None = None  # material icon name, e.g. "RESTAURANT"

    # Aggregate filled in by list queries (0 when unknown).
    total_spent: float = 0.0
    total_saved: float = 0.0

    @property
    def total(self) -> float:
        """Combined absolute money moved through this category."""
        return self.total_spent + self.total_saved


@dataclass(frozen=True)
class Entry:
    """A single logged transaction against a category."""

    id: int
    category_id: int
    amount: float
    type: EntryType
    entry_date: date
    note: str | None = None

    # Denormalized for list rendering (avoids an extra lookup per row).
    category_name: str = ""
    category_color: str = "#888888"
    category_icon: str | None = None

    @property
    def signed_amount(self) -> float:
        """Amount as +ve (saved) or -ve (spent) for balance math."""
        return self.amount if self.type is EntryType.SAVED else -self.amount


@dataclass(frozen=True)
class Summary:
    """Totals for a selected period."""

    spent: float = 0.0
    saved: float = 0.0

    @property
    def balance(self) -> float:
        """Saved minus spent for the period."""
        return self.saved - self.spent

    @property
    def is_empty(self) -> bool:
        return self.spent == 0 and self.saved == 0


@dataclass(frozen=True)
class DayTotal:
    """Spent/saved totals for a single calendar day (charts)."""

    day: date
    spent: float = 0.0
    saved: float = 0.0


@dataclass
class CategoryDraft:
    """Mutable form state used by the add/edit category dialog."""

    id: int | None = None
    name: str = ""
    color: str = ""
    icon: str | None = None


@dataclass
class EntryDraft:
    """Mutable form state used by the add/edit entry sheet."""

    id: int | None = None
    category_id: int | None = None
    amount: str = ""  # raw text from the field, parsed on save
    type: EntryType = EntryType.SPENT
    note: str = ""
    entry_date: date = field(default_factory=date.today)
