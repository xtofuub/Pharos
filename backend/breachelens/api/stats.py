"""Stats endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from breachelens.state import AppState
from .auth import get_state, require_session

router = APIRouter(tags=["stats"], dependencies=[Depends(require_session)])


@router.get("/api/stats")
async def stats(state: AppState = Depends(get_state)) -> dict:
    total_records = await state.db.fetchval("SELECT COUNT(*) FROM records")
    total_files = await state.db.fetchval("SELECT COUNT(*) FROM files")
    total_sources = await state.db.fetchval("SELECT COUNT(*) FROM sources")
    total_size = await state.db.fetchval("SELECT COALESCE(SUM(size_bytes), 0) FROM sources")
    last_job = await state.db.fetchval(
        "SELECT started_at FROM index_jobs ORDER BY id DESC LIMIT 1"
    )
    return {
        "total_records": total_records or 0,
        "total_files": total_files or 0,
        "total_sources": total_sources or 0,
        "total_size_bytes": total_size or 0,
        "last_indexing_job": last_job,
    }
