"""Profile reads/updates + member search (by username or phone)."""

from __future__ import annotations

from backend.auth import AuthError, require_uid
from backend.config import get_client
from backend.models import Profile
from backend.money import normalize_phone, normalize_username


def _c():
    return get_client()


def get_my_profile() -> Profile | None:
    from backend.auth import current_uid
    uid = current_uid()
    if not uid:
        return None
    rows = _c().table("profiles").select("*").eq("id", uid).execute().data
    if not rows:
        return None
    r = rows[0]
    return Profile(id=r["id"], name=r.get("name", ""), username=r.get("username", ""),
                   phone=r.get("phone", ""))


def update_my_profile(*, name: str, username: str | None = None) -> Profile:
    """Edit name (and username if free). Phone is immutable in v1."""
    c = _c()
    uid = require_uid()
    patch: dict = {}
    if (name or "").strip():
        patch["name"] = name.strip()
    if username:
        uname = normalize_username(username)
        taken = c.table("profiles").select("id").eq("username", uname).execute().data
        if taken and taken[0]["id"] != uid:
            raise ValueError("username is already taken")
        patch["username"] = uname
    if patch:
        c.table("profiles").update(patch).eq("id", uid).execute()
    return get_my_profile()


def search_user(query: str) -> list[Profile]:
    """Find registered users by exact username or phone (for adding members)."""
    c = _c()
    q = (query or "").strip()
    rows: list[dict] = []
    try:
        uname = normalize_username(q.lower())
        rows = c.table("profiles").select("*").eq("username", uname).execute().data
    except ValueError:
        pass
    if not rows:
        try:
            ph = normalize_phone(q)
            rows = c.table("profiles").select("*").eq("phone", ph).execute().data
        except ValueError:
            pass
    # Never leak email addresses in search results.
    return [Profile(id=r["id"], name=r.get("name", ""), username=r.get("username", ""),
                    phone=r.get("phone", "")) for r in rows]
