"""Auth flows over Supabase Auth (email sign-up with confirmation, login).

Session persistence: after login/sign-up the session dict is saved via
session_store so the user stays logged in across restarts.
"""

from __future__ import annotations

from typing import Any

from backend import session_store
from backend.config import get_client, get_settings
from backend.money import check_password, normalize_phone, normalize_username


class AuthError(Exception):
    pass


def _client():
    return get_client()


def _save_session(session, user) -> dict[str, Any]:
    data = {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "user_id": user.id,
        "email": getattr(user, "email", None),
    }
    session_store.save_session(data)
    return data


def sign_up(*, name: str, username: str, phone: str, email: str,
            password: str, confirm: str) -> dict[str, Any]:
    """Create an auth user + profile row. Raises AuthError on any problem."""
    name = (name or "").strip()
    if not name:
        raise AuthError("please enter your full name")
    uname = normalize_username(username)
    ph = normalize_phone(phone)
    email = (email or "").strip().lower()
    if "@" not in email:
        raise AuthError("enter a valid email address")
    try:
        check_password(password, confirm)
    except ValueError as exc:
        raise AuthError(str(exc)) from exc

    c = _client()
    # Best-effort pre-checks (anon clients may see no rows under RLS — the
    # DB unique constraints are the real guard, mapped below).
    try:
        if c.table("profiles").select("id").eq("username", uname).execute().data:
            raise AuthError("username is already taken")
        if c.table("profiles").select("id").eq("phone", ph).execute().data:
            raise AuthError("phone number is already registered")
    except AuthError:
        raise
    except Exception:
        pass

    try:
        res = c.auth.sign_up({
            "email": email, "password": password,
            "options": {"data": {"name": name, "username": uname, "phone": ph}},
        })
    except Exception as exc:
        raise AuthError(_friendly(exc)) from exc

    if res.session and res.user:
        _save_session(res.session, res.user)
        _ensure_profile(c, res.user.id, name, uname, ph, email)
        _claim_invites(c)
        return {"user_id": res.user.id, "confirmed": True}
    # Email confirmation required: no session yet (v1 flow). The profile row
    # is created on first login from the metadata above.
    return {"user_id": res.user.id if res.user else None, "confirmed": False}


def _ensure_profile(c, user_id: str, name: str, username: str, phone: str,
                    email: str = "") -> None:
    try:
        existing = c.table("profiles").select("id").eq("id", user_id).execute().data
    except Exception:
        return  # session-less caller (pre-confirmation); done at first login
    if not existing:
        try:
            c.table("profiles").insert(
                {"id": user_id, "name": name, "username": username,
                 "phone": phone, "email": email or None}
            ).execute()
        except Exception as exc:
            msg = str(exc).lower()
            if "duplicate" in msg or "already exists" in msg or "unique" in msg:
                return  # raced insert; row is there now
            raise


def _claim_invites(c) -> int:
    try:
        r = c.rpc("claim_phone_invites", {}).execute()
        return int(r.data or 0)
    except Exception:
        return 0


def login(*, login_id: str, password: str) -> dict[str, Any]:
    """Log in with email OR username. Returns {'user_id', 'email'}."""
    login_id = (login_id or "").strip()
    c = _client()
    email = login_id.lower()
    if "@" not in login_id:
        uname = normalize_username(login_id)
        try:
            found = c.rpc("lookup_email_by_username",
                          {"p_username": uname}).execute().data
        except Exception as exc:
            raise AuthError(
                "username login needs migration_usernamelogin.sql applied — "
                "or log in with email") from exc
        if not found:
            raise AuthError("no account with that username")
        email = found.lower()
    try:
        res = c.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        raise AuthError(_friendly(exc)) from exc
    _save_session(res.session, res.user)
    profile_ok = _ensure_profile_from_login(c, res.user)
    _claim_invites(c)
    result = {"user_id": res.user.id, "email": res.user.email}
    if not profile_ok:
        # Session is valid — let the user in; the profile screen explains
        # (usually: this phone/username is tied to another account) with
        # retry + logout instead of crashing or blocking login.
        result["profile_missing"] = True
    return result


def _ensure_profile_from_login(c, user) -> bool:
    """Create the profile row on first login (email-confirm flow creates the
    auth user before any session exists, so signup couldn't insert it)."""
    try:
        rows = c.table("profiles").select("id").eq("id", user.id).execute().data
        if rows:
            return True
        meta = getattr(user, "user_metadata", None) or {}
        email = getattr(user, "email", None) or meta.get("email", "")
        phone = meta.get("phone")
        if not phone:
            return False  # without a phone we can't satisfy the NOT NULL row
        c.table("profiles").insert({
            "id": user.id,
            "name": meta.get("name", (email or "Member").split("@")[0]),
            "username": meta.get("username", f"user_{user.id[:8]}"),
            "phone": phone,
            "email": email or None,
        }).execute()
        return True
    except Exception:
        return False


def logout() -> None:
    try:
        _client().auth.sign_out()
    except Exception:
        pass
    try:
        from backend.config import reset_client
        reset_client()
    except Exception:
        pass
    session_store.clear_session()


def current_uid() -> str | None:
    """Logged-in user id, or None — never raises (safe for every caller)."""
    try:
        resp = _client().auth.get_user()
        user = getattr(resp, "user", None)
        return getattr(user, "id", None)
    except Exception:
        return None


def require_uid() -> str:
    uid = current_uid()
    if not uid:
        raise AuthError("session expired — please log in again")
    return uid


def restore_session() -> dict[str, Any] | None:
    """Re-apply a saved session to the client. None if missing/expired."""
    saved = session_store.load_session()
    if not saved:
        return None
    s = get_settings()
    if not s.configured:
        return None
    c = _client()
    try:
        c.auth.set_session(saved["access_token"], saved.get("refresh_token", ""))
        user = c.auth.get_user()
        if not user or not user.user:
            raise AuthError("expired")
        # Refresh stored tokens (rotation).
        sess = getattr(user, "session", None)
        if sess is not None:
            _save_session(sess, user.user)
        _claim_invites(c)
        return {"user_id": user.user.id, "email": user.user.email}
    except Exception:
        session_store.clear_session()
        return None


def current_user_id() -> str | None:
    saved = session_store.load_session()
    return saved.get("user_id") if saved else None


def _friendly(exc: Exception) -> str:
    msg = str(exc).lower()
    if "already registered" in msg or "already exists" in msg:
        return "email is already registered — try logging in"
    if "invalid login" in msg or "invalid credential" in msg:
        return "wrong email/username or password"
    if "email not confirmed" in msg:
        return "please confirm your email (check your inbox), then log in"
    if "network" in msg or "fetch" in msg or "connection" in msg:
        return "no internet — check your connection and retry"
    return "authentication failed — please retry"
