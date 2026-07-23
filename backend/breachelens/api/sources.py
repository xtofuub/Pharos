"""Source folder management endpoints."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from breachelens.errors import BadRequestError, ForbiddenError
from breachelens.ingest.index_job import start_indexing
from breachelens.ingest.scanner import scan_folder
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
    start_indexing: bool = True


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


def _parse_extensions(value: str) -> list[str]:
    extensions = [part.strip().lower().lstrip(".") for part in value.split(",")]
    extensions = [ext for ext in extensions if ext]
    if not extensions:
        raise BadRequestError("at least one file extension is required")
    return extensions


def _pick_folder_native() -> str | None:
    """Open a native folder picker on the machine running Pharos."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("native folder picker is unavailable in this build") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            title="Choose a folder for Pharos to scan",
            mustexist=True,
        )
        return selected or None
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


@router.post("/api/sources/pick")
async def pick_source_folder() -> dict:
    if os.name != "nt":
        return {
            "supported": False,
            "path": None,
            "error": "native folder selection is currently available in the Windows executable",
        }
    try:
        selected = await asyncio.to_thread(_pick_folder_native)
    except Exception as exc:
        return {"supported": False, "path": None, "error": str(exc)}
    return {"supported": True, "path": selected, "cancelled": selected is None}


@router.post("/api/sources/preview")
async def preview_source(req: AddSourceRequest) -> dict:
    canonical = validate_source_folder(req.path)
    allowed_exts = req.allowed_extensions or ".txt,.csv,.tsv,.log,.jsonl,.sql"
    extensions = _parse_extensions(allowed_exts)
    files = await asyncio.to_thread(scan_folder, canonical, extensions)
    total_bytes = sum(item.size_bytes for item in files)
    return {
        "valid": True,
        "canonical_path": str(canonical),
        "files_count": len(files),
        "size_bytes": total_bytes,
        "extensions": sorted({item.extension for item in files}),
        "sample_files": [str(item.path.relative_to(canonical)) for item in files[:8]],
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

    allowed_exts = req.allowed_extensions or ".txt,.csv,.tsv,.log,.jsonl,.sql"
    extensions = _parse_extensions(allowed_exts)
    preview_files = await asyncio.to_thread(scan_folder, canonical, extensions)
    if not preview_files:
        raise BadRequestError(
            "no supported files were found in this folder or its subfolders; "
            f"allowed extensions: {', '.join('.' + ext for ext in extensions)}"
        )

    existing = await state.db.fetchone("SELECT id FROM sources WHERE path = ?", (str(canonical),))
    if existing is not None:
        source_id = int(existing["id"])
        await state.db.execute(
            """
            UPDATE sources
            SET display_name = COALESCE(?, display_name), storage_mode = ?,
                allowed_extensions = ?, status = 'pending'
            WHERE id = ?
            """,
            (req.display_name, storage_mode, allowed_exts, source_id),
        )
    else:
        cur = await state.db.execute(
            """
            INSERT INTO sources (
                path, display_name, storage_mode, allowed_extensions, status,
                files_count, size_bytes, authorized_by, authorized_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, datetime('now'))
            """,
            (
                str(canonical),
                req.display_name,
                storage_mode,
                allowed_exts,
                len(preview_files),
                sum(item.size_bytes for item in preview_files),
                session.username,
            ),
        )
        source_id = int(cur.lastrowid or 0)

    job_id = None
    if req.start_indexing:
        job_id = await start_indexing(state, source_id)

    return {
        "id": source_id,
        "path": str(canonical),
        "status": "indexing" if job_id is not None else "pending",
        "job_id": job_id,
        "files_found": len(preview_files),
    }


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
