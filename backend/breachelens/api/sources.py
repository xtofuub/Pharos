"""Source-folder management, native picking, and scan preview endpoints."""
from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterable
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from breachelens.errors import ConflictError, ForbiddenError, IndexingError
from breachelens.ingest.index_job import get_current_job, start_indexing
from breachelens.ingest.scanner import normalize_extensions, scan_folder_detailed
from breachelens.native_dialogs import pick_folder
from breachelens.security.validation import validate_source_folder
from breachelens.state import AppState
from .auth import SessionInfo, get_state, require_session

router = APIRouter(tags=["sources"], dependencies=[Depends(require_session)])

DEFAULT_EXTENSIONS = ".txt,.csv,.tsv,.log,.jsonl,.json,.sql,.lst,.dat"


class AddSourceRequest(BaseModel):
    path: str
    display_name: Optional[str] = None
    storage_mode: Optional[str] = None
    allowed_extensions: Optional[str] = None
    authorized: bool = False
    auto_index: bool = True


class ScanPreviewRequest(BaseModel):
    path: str
    allowed_extensions: Optional[str] = None


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
    last_error: Optional[str] = None


def _parse_extensions(raw: str | None) -> list[str]:
    values: Iterable[str] = (raw or DEFAULT_EXTENSIONS).split(",")
    return normalize_extensions(values)


def _serialize_extensions(values: Iterable[str]) -> str:
    return ",".join(f".{value}" for value in normalize_extensions(values))


@router.get("/api/sources", response_model=List[SourceResponse])
async def list_sources(state: AppState = Depends(get_state)) -> List[SourceResponse]:
    rows = await state.db.fetchall(
        """
        SELECT s.id, s.path, s.display_name, s.storage_mode, s.allowed_extensions, s.status,
               s.files_count, s.records_count, s.size_bytes, s.last_indexed_at, s.created_at,
               (
                   SELECT j.error_message
                   FROM index_jobs j
                   WHERE j.source_id = s.id AND j.error_message IS NOT NULL
                   ORDER BY j.id DESC LIMIT 1
               ) AS last_error
        FROM sources s
        ORDER BY s.id
        """
    )
    return [SourceResponse(**dict(row)) for row in rows]


@router.post("/api/system/pick-folder")
async def pick_source_folder() -> dict:
    selected = await asyncio.to_thread(pick_folder)
    if not selected:
        return {"selected": False, "path": None}
    canonical = validate_source_folder(selected)
    return {"selected": True, "path": str(canonical)}


@router.post("/api/sources/scan-preview")
async def scan_preview(
    req: ScanPreviewRequest,
    state: AppState = Depends(get_state),
) -> dict:
    canonical = validate_source_folder(req.path)
    extensions = _parse_extensions(req.allowed_extensions)
    max_size = state.config.indexing.max_file_size_mb * 1024 * 1024
    result = await asyncio.to_thread(
        scan_folder_detailed,
        canonical,
        extensions,
        max_file_size_bytes=max_size,
    )
    return {
        "valid": True,
        "canonical_path": str(canonical),
        "files_count": len(result.files),
        "size_bytes": result.total_bytes,
        "extension_counts": result.extension_counts,
        "skipped_directories": result.skipped_directories,
        "skipped_files": result.skipped_files,
        "skipped_large_files": result.skipped_large_files,
        "warnings": result.errors[:10],
        "sample_files": [str(item.path.relative_to(canonical)) for item in result.files[:8]],
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
        from breachelens.errors import BadRequestError

        raise BadRequestError(f"invalid storage_mode: {storage_mode}")

    allowed_exts = _serialize_extensions(_parse_extensions(req.allowed_extensions))
    display_name = req.display_name or canonical.name or str(canonical)

    try:
        cur = await state.db.execute(
            """
            INSERT INTO sources (
                path, display_name, storage_mode, allowed_extensions, status,
                authorized_by, authorized_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, datetime('now'))
            """,
            (str(canonical), display_name, storage_mode, allowed_exts, session.username),
        )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"source folder is already added: {canonical}") from exc

    source_id = int(cur.lastrowid or 0)
    response: dict = {
        "id": source_id,
        "path": str(canonical),
        "status": "pending",
        "job_id": None,
    }

    if req.auto_index:
        if get_current_job() is None:
            try:
                response["job_id"] = await start_indexing(state, source_id)
                response["status"] = "indexing"
            except IndexingError as exc:
                response["warning"] = str(exc)
        else:
            response["warning"] = "another folder is already being indexed; use Reindex when it finishes"

    return response


@router.delete("/api/sources/{source_id}")
async def delete_source(source_id: int, state: AppState = Depends(get_state)) -> dict:
    active = get_current_job()
    if active is not None and active.source_id == source_id:
        raise ConflictError("cannot delete a source while it is being indexed")

    # FTS5 rows do not participate in normal SQLite foreign-key cascades.
    rows = await state.db.fetchall(
        "SELECT fts_rowid FROM records WHERE source_id = ?",
        (source_id,),
    )
    async with state.db._lock:
        for row in rows:
            await state.db.conn.execute("DELETE FROM records_fts WHERE rowid = ?", (row["fts_rowid"],))
        await state.db.conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        await state.db.conn.commit()
    return {"deleted": source_id}


@router.post("/api/sources/validate")
async def validate_source(req: ScanPreviewRequest) -> dict:
    try:
        canonical = validate_source_folder(req.path)
        return {"valid": True, "canonical_path": str(canonical)}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}
