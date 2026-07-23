"""Indexing control endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from breachelens.ingest.index_job import (
    cancel_indexing,
    get_current_job,
    list_jobs,
    start_indexing,
)
from breachelens.state import AppState
from .auth import get_state, require_session

router = APIRouter(tags=["indexing"], dependencies=[Depends(require_session)])


@router.post("/api/index/start/{source_id}")
async def start_index(source_id: int, state: AppState = Depends(get_state)) -> dict:
    job_id = await start_indexing(state, source_id)
    return {"job_id": job_id, "status": "running"}


@router.post("/api/index/cancel")
async def cancel(state: AppState = Depends(get_state)) -> dict:
    await cancel_indexing(state)
    return {"status": "cancelled"}


@router.get("/api/index/status")
async def status(state: AppState = Depends(get_state)) -> dict | None:
    snap = get_current_job()
    if snap is None:
        return None
    return {
        "job_id": snap.job_id,
        "source_id": snap.source_id,
        "status": snap.status,
        "started_at": snap.started_at,
        "current_file": snap.current_file,
        "files_total": snap.files_total,
        "files_processed": snap.files_processed,
        "files_skipped": snap.files_skipped,
        "records_indexed": snap.records_indexed,
        "errors": snap.errors,
        "lines_per_sec": snap.lines_per_sec,
        "mb_per_sec": snap.mb_per_sec,
        "elapsed_secs": snap.elapsed_secs,
        "eta_secs": snap.eta_secs,
    }


@router.get("/api/index/jobs")
async def jobs(state: AppState = Depends(get_state)) -> list[dict]:
    return await list_jobs(state, limit=20)
