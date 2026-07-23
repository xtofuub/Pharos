"""Source folder management endpoints."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from breachelens.errors import ForbiddenError, BadRequestError
from breachelens.ingest.scanner import scan_folder_detailed
from breachelens.security.validation import validate_source_folder
from breachelens.state import AppState
from .auth import get_state, require_session, SessionInfo

router = APIRouter(tags=["sources"], dependencies=[Depends(require_session)])


class AddSourceRequest(BaseModel):
    path: str
    display_name: Optional[str] = None
    storage_mode: Optional[str] = None
    allowed_extensions: Optional[str] = None
    authorized: bool = False


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


def _extensions(value: Optional[str]) -> list[str]:
    raw = value or ".txt,.csv,.tsv,.log,.jsonl,.sql"
    return [part.strip().lower().lstrip(".") for part in raw.split(",") if part.strip()]


def _choose_folder_dialog() -> str:
    """Open a native OS folder picker on the machine running Pharos."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError(f"native folder picker is unavailable: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(title="Choose a folder for Pharos to scan", mustexist=True)
        return selected or ""
    finally:
        root.destroy()


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


@router.post("/api/sources/pick-folder")
async def pick_folder() -> dict:
    try:
        selected = await asyncio.to_thread(_choose_folder_dialog)
    except Exception as exc:
        raise BadRequestError(str(exc)) from exc
    if not selected:
        return {"selected": False, "path": None}
    canonical = validate_source_folder(selected)
    return {"selected": True, "path": str(canonical)}


@router.post("/api/sources/preview")
async def preview_source(req: AddSourceRequest) -> dict:
    canonical = validate_source_folder(req.path)
    exts = _extensions(req.allowed_extensions)
    result = await asyncio.to_thread(scan_folder_detailed, canonical, exts)
    total_size = sum(item.size_bytes for item in result.files)
    return {
        "valid": True,
        "canonical_path": str(canonical),
        "matching_files": len(result.files),
        "total_size_bytes": total_size,
        "folders_visited": result.folders_visited,
        "files_seen": result.files_seen,
        "files_ignored": result.files_ignored,
        "errors": result.errors[:25],
        "sample_files": [str(item.path) for item in result.files[:10]],
        "allowed_extensions": exts,
    }


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
        raise BadRequestError(f"invalid storage_mode: {storage_mode}")
    allowed_exts = ",".join(f".{ext}" for ext in _extensions(req.allowed_extensions))

    existing = await state.db.fetchone("SELECT id FROM sources WHERE path = ?", (str(canonical),))
    if existing is not None:
        return {"id": existing["id"], "path": str(canonical), "status": "already_added"}

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
async def validate_source(req: AddSourceRequest) -> dict:
    try:
        canonical = validate_source_folder(req.path)
        return {"valid": True, "canonical_path": str(canonical)}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}
