"""Paise money helpers + input validators shared by backend and UI.

Rule: store/compute in INTEGER paise everywhere in the cloud layer.
Format as ₹ only for display.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
JOIN_CODE_RE = re.compile(r"^[A-Z2-9]{6}$")


def to_paise(amount: str | float | Decimal) -> int:
    """Parse a rupee amount ('1,250.50', 1250.5) into integer paise."""
    if isinstance(amount, (int,)):
        # Bare int means rupees only when it comes from UI text; treat as ₹.
        return amount * 100
    s = str(amount).strip().replace(",", "").replace("₹", "").replace("Rs", "")
    try:
        d = (Decimal(s) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid amount: {amount!r}") from exc
    if d <= 0:
        raise ValueError("amount must be greater than zero")
    return int(d)


def format_inr(paise: int) -> str:
    """Format integer paise as ₹1,250.00 (negative keeps the sign up front)."""
    sign = "-" if paise < 0 else ""
    a = abs(int(paise))
    return f"{sign}₹{a // 100:,}.{a % 100:02d}"


def normalize_phone(raw: str) -> str:
    """Normalize Indian numbers to +91XXXXXXXXXX. Raises ValueError if bad."""
    digits = re.sub(r"\D", "", (raw or "").strip())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("enter a valid 10-digit Indian mobile number")
    return "+91" + digits


def normalize_username(raw: str) -> str:
    u = (raw or "").strip().lower()
    if not USERNAME_RE.match(u):
        raise ValueError("username: 3-20 chars, lowercase letters/digits/_")
    return u


def check_password(pw: str, confirm: str) -> None:
    if len(pw or "") < 8:
        raise ValueError("password must be at least 8 characters")
    if pw != confirm:
        raise ValueError("passwords do not match")


def check_trip_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise ValueError("trip name: 1-80 characters")
    return name
