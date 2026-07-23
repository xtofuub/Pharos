"""Argon2id password hashing + in-memory sessions."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, phc: str) -> bool:
    try:
        return _pwd_context.verify(password, phc)
    except Exception:
        return False


@dataclass
class Session:
    token: str
    user_id: int
    username: str
    created_at: float = field(default_factory=time.monotonic)
    expires_at: float = 0.0


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}

    def create(self, user_id: int, username: str, ttl_secs: int) -> Session:
        token = secrets.token_urlsafe(48)
        now = time.monotonic()
        session = Session(
            token=token,
            user_id=user_id,
            username=username,
            created_at=now,
            expires_at=now + ttl_secs,
        )
        self._sessions[token] = session
        return session

    def validate(self, token: str) -> Optional[Session]:
        s = self._sessions.get(token)
        if s is None:
            return None
        if s.expires_at < time.monotonic():
            self._sessions.pop(token, None)
            return None
        return s

    def revoke(self, token: str) -> None:
        self._sessions.pop(token, None)

    def cleanup_expired(self) -> None:
        now = time.monotonic()
        expired = [t for t, s in self._sessions.items() if s.expires_at < now]
        for t in expired:
            self._sessions.pop(t, None)
