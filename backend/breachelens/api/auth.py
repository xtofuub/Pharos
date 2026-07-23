"""Auth middleware + login/logout endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from breachelens.errors import UnauthorizedError
from breachelens.state import AppState

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    must_change_password: bool


def get_state(request: Request) -> AppState:
    return request.app.state.app_state


async def require_session(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> "SessionInfo":
    """FastAPI dependency: require a valid Bearer session token."""
    state: AppState = request.app.state.app_state
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    token = authorization[len("Bearer "):]
    session = state.sessions.validate(token)
    if session is None:
        raise UnauthorizedError("invalid or expired session")
    return SessionInfo(token=token, user_id=session.user_id, username=session.username)


class SessionInfo:
    def __init__(self, token: str, user_id: int, username: str) -> None:
        self.token = token
        self.user_id = user_id
        self.username = username


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, state: AppState = Depends(get_state)) -> LoginResponse:
    row = await state.db.fetchone(
        "SELECT id, username, password_hash, must_change_password FROM users WHERE username = ?",
        (req.username,),
    )
    if row is None:
        raise UnauthorizedError("invalid credentials")
    from breachelens.security.auth import verify_password

    if not verify_password(req.password, row["password_hash"]):
        raise UnauthorizedError("invalid credentials")

    await state.db.execute(
        "UPDATE users SET last_login_at = datetime('now') WHERE id = ?",
        (row["id"],),
    )
    session = state.sessions.create(
        user_id=row["id"],
        username=row["username"],
        ttl_secs=state.config.auth.session_lifetime_secs,
    )
    return LoginResponse(
        token=session.token,
        username=session.username,
        must_change_password=bool(row["must_change_password"]),
    )


@router.post("/auth/logout")
async def logout(session: SessionInfo = Depends(require_session), state: AppState = Depends(get_state)) -> dict:
    state.sessions.revoke(session.token)
    return {"status": "logged_out"}
