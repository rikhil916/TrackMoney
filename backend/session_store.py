"""Secure on-device session storage (so login survives restarts).

Stores the Supabase session (access/refresh tokens + user id/email) as a
0600 JSON file under ~/.trackmoney/. Web/desktop parity is kept by preferring
this file; screens should additionally mirror nothing sensitive in UI state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _path() -> Path:
    root = Path.home() / ".trackmoney"
    root.mkdir(parents=True, exist_ok=True)
    return root / "session.json"


def save_session(data: dict[str, Any]) -> None:
    p = _path()
    p.write_text(json.dumps(data))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def load_session() -> dict[str, Any] | None:
    p = _path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def clear_session() -> None:
    try:
        _path().unlink(missing_ok=True)
    except OSError:
        pass
