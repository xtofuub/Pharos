"""Authentication, session enforcement, and mandatory first-login password change."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from breachelens.errors import BadRequestError, ForbiddenError, UnauthorizedError
from breachelens.security.auth import hash_password, verify_password
from breachelens.state import AppState

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def get_state(request: Request) -> AppState:
    return request.app.state.app_state


class SessionInfo:
    def __init__(self, token: str, user_id: int, username: str, must_change_password: bool = False) -> None:
        self.token = token
        self.user_id = user_id
        self.username = username
        self.must_change_password = must_change_password


async def require_session(request: Request, authorization: Optional[str] = Header(None)) -> SessionInfo:
    state: AppState = request.app.state.app_state
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    token = authorization[len("Bearer "):]
    session = state.sessions.validate(token)
    if session is None:
        raise UnauthorizedError("invalid or expired session")

    user = await state.db.fetchone("SELECT must_change_password FROM users WHERE id = ?", (session.user_id,))
    if user is None:
        state.sessions.revoke(token)
        raise UnauthorizedError("user no longer exists")
    must_change = bool(user["must_change_password"])
    if must_change and request.url.path not in {"/auth/change-password", "/auth/logout"}:
        raise ForbiddenError("password change required before using Pharos")
    return SessionInfo(token, session.user_id, session.username, must_change)


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, state: AppState = Depends(get_state)) -> LoginResponse:
    row = await state.db.fetchone(
        "SELECT id, username, password_hash, must_change_password FROM users WHERE username = ?",
        (req.username.strip(),),
    )
    if row is None or not verify_password(req.password, row["password_hash"]):
        raise UnauthorizedError("invalid credentials")
    await state.db.execute("UPDATE users SET last_login_at=datetime('now') WHERE id=?", (row["id"],))
    session = state.sessions.create(user_id=row["id"], username=row["username"], ttl_secs=state.config.auth.session_lifetime_secs)
    return LoginResponse(token=session.token, username=session.username, must_change_password=bool(row["must_change_password"]))


@router.post("/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    session: SessionInfo = Depends(require_session),
    state: AppState = Depends(get_state),
) -> dict:
    row = await state.db.fetchone("SELECT password_hash FROM users WHERE id=?", (session.user_id,))
    if row is None or not verify_password(body.current_password, row["password_hash"]):
        raise UnauthorizedError("current password is incorrect")
    password = body.new_password
    if len(password) < 10:
        raise BadRequestError("new password must be at least 10 characters")
    if password.lower() in {"breachelens", "pharos", "password123", "adminadmin"}:
        raise BadRequestError("choose a less predictable password")
    await state.db.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?", (hash_password(password), session.user_id))
    return {"changed": True}


@router.post("/auth/logout")
async def logout(session: SessionInfo = Depends(require_session), state: AppState = Depends(get_state)) -> dict:
    state.sessions.revoke(session.token)
    return {"status": "logged_out"}
