"""Supabase configuration: .env loading + client factory.

Keys live in a .env file (see .env.example). Only the public anon key is
ever used in the app — never the service_role key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # optional dependency; env vars still work
    def load_dotenv(*a, **k):
        return False


@dataclass(frozen=True)
class Settings:
    url: str
    anon_key: str

    @property
    def configured(self) -> bool:
        return bool(self.url and self.anon_key and "example" not in self.url)


def _find_env() -> Path:
    here = Path(__file__).resolve().parent.parent
    for cand in (here / ".env", Path.cwd() / ".env"):
        if cand.exists():
            return cand
    return here / ".env"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(_find_env())
    return Settings(
        url=os.environ.get("SUPABASE_URL", "").strip(),
        anon_key=os.environ.get("SUPABASE_ANON_KEY", "").strip(),
    )


def get_client():
    """Return the shared supabase client (singleton).

    Singleton is required: login/restore store the session on this instance
    via ``auth.set_session``. A fresh client per call would lose the session
    and every later call would run anonymously (RLS denials, missing user).
    """
    global _CLIENT
    if _CLIENT is None:
        from supabase import create_client

        s = get_settings()
        if not s.configured:
            raise RuntimeError(
                "Supabase is not configured. Copy .env.example to .env and fill "
                "in SUPABASE_URL / SUPABASE_ANON_KEY."
            )
        _CLIENT = create_client(s.url, s.anon_key)
    return _CLIENT


def reset_client() -> None:
    """Drop the shared client (logout) so no stale session survives."""
    global _CLIENT
    _CLIENT = None


_CLIENT = None
