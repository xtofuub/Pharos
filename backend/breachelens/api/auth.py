"""Local desktop request context.

Pharos is a loopback-only desktop tool and intentionally has no login,
password, bearer token, or session flow. The lightweight SessionInfo object
is kept only so existing audit code can label actions consistently.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from breachelens.state import AppState

router = APIRouter(tags=["local"])


def get_state(request: Request) -> AppState:
    return request.app.state.app_state


class SessionInfo:
    def __init__(self, username: str = "local") -> None:
        self.token = ""
        self.user_id = 0
        self.username = username
        self.must_change_password = False


async def require_session(request: Request) -> SessionInfo:
    """Return the local desktop operator without requiring credentials."""
    return SessionInfo()
