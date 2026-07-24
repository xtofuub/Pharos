"""Settings endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from breachelens.state import AppState
from .auth import SessionInfo, get_state, require_session

router = APIRouter(tags=["settings"], dependencies=[Depends(require_session)])


class UpdateSettingRequest(BaseModel):
    key: str
    value: str


@router.get("/api/settings")
async def get_settings(state: AppState = Depends(get_state)) -> dict:
    cfg = state.config
    return {
        "server": cfg.server.model_dump(),
        "storage": cfg.storage.model_dump(),
        "indexing": cfg.indexing.model_dump(),
        "search": cfg.search.model_dump(),
        "regex_safety": cfg.regex_safety.model_dump(),
        "audit": cfg.audit.model_dump(),
    }


@router.post("/api/settings")
async def update_setting(
    body: UpdateSettingRequest,
    session: SessionInfo = Depends(require_session),
    state: AppState = Depends(get_state),
) -> dict:
    await state.db.execute(
        """
        INSERT INTO settings (key, value, updated_at, updated_by)
        VALUES (?, ?, datetime('now'), ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at,
            updated_by = excluded.updated_by
        """,
        (body.key, body.value, session.username),
    )
    return {"updated": body.key}
