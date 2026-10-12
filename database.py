"""SQLite data layer for TrackMoney.

Every query lives here so the UI never talks to SQL directly. The module
imports only the standard library + models, keeping it independent from Flet.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from models import Category, DayTotal, Entry, EntryType, Summary

# Reasonable default so a fresh install has something to show.
DEFAULT_CATEGORIES = [
    ("Food & Dining", "#E85D3F", "RESTAURANT"),
    ("Groceries", "#4CAF50", "LOCAL_GROCERY_STORE"),
    ("Transport", "#2196F3", "DIRECTIONS_BUS"),
    ("Shopping", "#9C27B0", "SHOPPING_BAG"),
    ("Bills & Utilities", "#FF9800", "RECEIPT_LONG"),
    ("Health", "#009688", "FAVORITE"),
    ("Entertainment", "#3F51B5", "MOVIE"),
    ("Salary", "#673AB7", "ACCOUNT_BALANCE"),
    ("Savings", "#607D8B", "SAVINGS"),
]


class Database:
    """Thin wrapper around a SQLite connection with typed helpers."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        # check_same_thread=False: Flet may call from a worker thread.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()
        self._seed_if_empty()

    # ------------------------------------------------------------- setup --

    def _migrate(self) -> None:
        """Create tables if they do not exist yet (idempotent)."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                color TEXT    NOT NULL,
                icon  TEXT
            );

            CREATE TABLE IF NOT EXISTS entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                amount      REAL    NOT NULL CHECK (amount > 0),
                type        TEXT    NOT NULL CHECK (type IN ('spent','saved')),
                note        TEXT,
                entry_date  TEXT    NOT NULL,          -- ISO 'YYYY-MM-DD'
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(entry_date);
            CREATE INDEX IF NOT EXISTS idx_entries_cat  ON entries(category_id);
            """
        )
        self.conn.commit()

    def _seed_if_empty(self) -> None:
        """Insert starter categories the first time the app runs."""
        count = self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if count == 0:
            self.conn.executemany(
                "INSERT INTO categories (name, color, icon) VALUES (?, ?, ?)",
                DEFAULT_CATEGORIES,
            )
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --------------------------------------------------------- categories --

    def list_categories(self) -> list[Category]:
        """All categories with their all-time spent/saved totals."""
        rows = self.conn.execute(
            """
            SELECT c.id, c.name, c.color, c.icon,
                   COALESCE(SUM(CASE WHEN e.type='spent' THEN e.amount END), 0) AS spent,
                   COALESCE(SUM(CASE WHEN e.type='saved' THEN e.amount END), 0) AS saved
            FROM categories c
            LEFT JOIN entries e ON e.category_id = c.id
            GROUP BY c.id
            ORDER BY c.name COLLATE NOCASE
            """
        ).fetchall()
        return [
            Category(
                id=r["id"], name=r["name"], color=r["color"], icon=r["icon"],
                total_spent=float(r["spent"]), total_saved=float(r["saved"]),
            )
            for r in rows
        ]

    def get_category(self, category_id: int) -> Category | None:
        r = self.conn.execute(
            "SELECT id, name, color, icon FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if r is None:
            return None
        return Category(id=r["id"], name=r["name"], color=r["color"], icon=r["icon"])

    def category_name_exists(self, name: str, exclude_id: int | None = None) -> bool:
        """Case-insensitive duplicate check used by validation."""
        q = "SELECT 1 FROM categories WHERE name = ? COLLATE NOCASE"
        params: list[object] = [name.strip()]
        if exclude_id is not None:
            q += " AND id != ?"
            params.append(exclude_id)
        return self.conn.execute(q, params).fetchone() is not None

    def create_category(self, name: str, color: str, icon: str | None) -> int:
        cur = self.conn.execute(
            "INSERT INTO categories (name, color, icon) VALUES (?, ?, ?)",
            (name.strip(), color, icon),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_category(self, category_id: int, name: str, color: str, icon: str | None) -> None:
        self.conn.execute(
            "UPDATE categories SET name = ?, color = ?, icon = ? WHERE id = ?",
            (name.strip(), color, icon, category_id),
        )
        self.conn.commit()

    def count_category_entries(self, category_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM entries WHERE category_id = ?", (category_id,)
        ).fetchone()
        return int(row[0])

    def delete_category(self, category_id: int, delete_entries: bool) -> int:
        """Delete a category. Returns how many entries were removed.

        With delete_entries=False the entries are kept but reassigned is not
        supported (no "uncategorized"), so callers should warn first; we
        default to cascading delete via the FK, but this flag lets the UI
        explicitly choose.
        """
        if delete_entries:
            n = self.count_category_entries(category_id)
            self.conn.execute("DELETE FROM entries WHERE category_id = ?", (category_id,))
        else:
            n = 0
        self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        self.conn.commit()
        return n

    # ------------------------------------------------------------ entries --

    def add_entry(
        self, category_id: int, amount: float, type: EntryType, entry_date: date,
        note: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO entries (category_id, amount, type, note, entry_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (category_id, amount, type.value, note, entry_date.isoformat()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_entry(
        self, entry_id: int, category_id: int, amount: float, type: EntryType,
        entry_date: date, note: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE entries
            SET category_id = ?, amount = ?, type = ?, entry_date = ?, note = ?
            WHERE id = ?
            """,
            (category_id, amount, type.value, entry_date.isoformat(), note, entry_id),
        )
        self.conn.commit()

    def delete_entry(self, entry_id: int) -> None:
        self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        self.conn.commit()

    def get_entry(self, entry_id: int) -> Entry | None:
        r = self.conn.execute(
            """
            SELECT e.*, c.name AS cat_name, c.color AS cat_color, c.icon AS cat_icon
            FROM entries e JOIN categories c ON c.id = e.category_id
            WHERE e.id = ?
            """,
            (entry_id,),
        ).fetchone()
        return self._row_to_entry(r) if r else None

    def list_entries(
        self, start: date | None = None, end: date | None = None,
        limit: int | None = None,
    ) -> list[Entry]:
        """Entries newest-first, optionally bounded by an inclusive date range."""
        q = """
            SELECT e.*, c.name AS cat_name, c.color AS cat_color, c.icon AS cat_icon
            FROM entries e JOIN categories c ON c.id = e.category_id
            WHERE 1=1
        """
        params: list[object] = []
        if start is not None:
            q += " AND e.entry_date >= ?"
            params.append(start.isoformat())
        if end is not None:
            q += " AND e.entry_date <= ?"
            params.append(end.isoformat())
        q += " ORDER BY e.entry_date DESC, e.id DESC"
        if limit is not None:
            q += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(q, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    # --------------------------------------------------------- analytics --

    def summary(self, start: date, end: date) -> Summary:
        """Spent/saved totals for an inclusive date range."""
        r = self.conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type='spent' THEN amount END), 0) AS spent,
                COALESCE(SUM(CASE WHEN type='saved' THEN amount END), 0) AS saved
            FROM entries WHERE entry_date BETWEEN ? AND ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchone()
        return Summary(spent=float(r["spent"]), saved=float(r["saved"]))

    def category_breakdown(self, start: date, end: date, type: EntryType) -> list[tuple[Category, float]]:
        """Per-category totals of one type for the pie chart, largest first."""
        rows = self.conn.execute(
            """
            SELECT c.id, c.name, c.color, c.icon, COALESCE(SUM(e.amount), 0) AS total
            FROM entries e JOIN categories c ON c.id = e.category_id
            WHERE e.entry_date BETWEEN ? AND ? AND e.type = ?
            GROUP BY c.id
            HAVING total > 0
            ORDER BY total DESC
            """,
            (start.isoformat(), end.isoformat(), type.value),
        ).fetchall()
        cats = [
            (Category(id=r["id"], name=r["name"], color=r["color"], icon=r["icon"]),
             float(r["total"]))
            for r in rows
        ]
        return cats

    def daily_totals(self, start: date, end: date) -> list[DayTotal]:
        """Spent/saved per day across the range, filling empty days with 0."""
        rows = self.conn.execute(
            """
            SELECT entry_date,
                   COALESCE(SUM(CASE WHEN type='spent' THEN amount END), 0) AS spent,
                   COALESCE(SUM(CASE WHEN type='saved' THEN amount END), 0) AS saved
            FROM entries WHERE entry_date BETWEEN ? AND ?
            GROUP BY entry_date
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        by_day = {
            date.fromisoformat(r["entry_date"]): (float(r["spent"]), float(r["saved"]))
            for r in rows
        }
        out: list[DayTotal] = []
        cur = start
        while cur <= end:
            spent, saved = by_day.get(cur, (0.0, 0.0))
            out.append(DayTotal(day=cur, spent=spent, saved=saved))
            cur += timedelta(days=1)
        return out

    # ------------------------------------------------------------- utils --

    @staticmethod
    def _row_to_entry(r: sqlite3.Row) -> Entry:
        return Entry(
            id=r["id"],
            category_id=r["category_id"],
            amount=float(r["amount"]),
            type=EntryType(r["type"]),
            entry_date=date.fromisoformat(r["entry_date"]),
            note=r["note"],
            category_name=r["cat_name"],
            category_color=r["cat_color"],
            category_icon=r["cat_icon"],
        )
