"""Source folder management endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from breachelens.errors import ForbiddenError
from breachelens.security.validation import validate_source_folder
from breachelens.state import AppState
from .auth import get_state, require_session, SessionInfo

router = APIRouter(tags=["sources"], dependencies=[Depends(require_session)])


class AddSourceRequest(BaseModel):
    path: str
    display_name: Optional[str] = None
    storage_mode: Optional[str] = None
    allowed_extensions: Optional[str] = None
    authorized: bool


class SourceResponse(BaseModel):
    id: int
    path: str
    display_name: Optional[str] = None
    storage_mode: str
    allowed_extensions: str
    status: str
    files_count: int
    records_count: int
    size_bytes: int
    last_indexed_at: Optional[str] = None
    created_at: str


@router.get("/api/sources", response_model=List[SourceResponse])
async def list_sources(state: AppState = Depends(get_state)) -> List[SourceResponse]:
    rows = await state.db.fetchall(
        """
        SELECT id, path, display_name, storage_mode, allowed_extensions, status,
               files_count, records_count, size_bytes, last_indexed_at, created_at
        FROM sources ORDER BY id
        """
    )
    return [SourceResponse(**dict(r)) for r in rows]


@router.post("/api/sources", response_model=dict)
async def add_source(
    req: AddSourceRequest,
    session: SessionInfo = Depends(require_session),
    state: AppState = Depends(get_state),
) -> dict:
    if not req.authorized:
        raise ForbiddenError("must confirm dataset authorization")

    canonical = validate_source_folder(req.path)
    storage_mode = req.storage_mode or state.config.storage.default_mode
    if storage_mode not in ("offset", "full"):
        from breachelens.errors import BadRequestError
        raise BadRequestError(f"invalid storage_mode: {storage_mode}")
    allowed_exts = req.allowed_extensions or ".txt,.csv,.tsv,.log,.jsonl,.sql"

    cur = await state.db.execute(
        """
        INSERT INTO sources (path, display_name, storage_mode, allowed_extensions, status, authorized_by, authorized_at)
        VALUES (?, ?, ?, ?, 'pending', ?, datetime('now'))
        """,
        (str(canonical), req.display_name, storage_mode, allowed_exts, session.username),
    )
    return {"id": cur.lastrowid, "path": str(canonical), "status": "pending"}


@router.delete("/api/sources/{source_id}")
async def delete_source(source_id: int, state: AppState = Depends(get_state)) -> dict:
    await state.db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    return {"deleted": source_id}


@router.post("/api/sources/validate")
async def validate_source(req: AddSourceRequest, state: AppState = Depends(get_state)) -> dict:
    try:
        canonical = validate_source_folder(req.path)
        return {"valid": True, "canonical_path": str(canonical)}
    except Exception as e:
        return {"valid": False, "error": str(e)}
