"""Indexing control endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from breachelens.ingest.index_job import (
    cancel_indexing,
    get_current_job,
    list_job_errors,
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
    return {"status": "cancelling"}


@router.get("/api/index/status")
async def status(state: AppState = Depends(get_state)) -> dict | None:
    snapshot = get_current_job()
    if snapshot is None:
        return None
    return {
        "job_id": snapshot.job_id,
        "source_id": snapshot.source_id,
        "status": snapshot.status,
        "started_at": snapshot.started_at,
        "current_file": snapshot.current_file,
        "files_total": snapshot.files_total,
        "files_processed": snapshot.files_processed,
        "files_skipped": snapshot.files_skipped,
        "records_indexed": snapshot.records_indexed,
        "errors": snapshot.errors,
        "lines_per_sec": snapshot.lines_per_sec,
        "mb_per_sec": snapshot.mb_per_sec,
        "elapsed_secs": snapshot.elapsed_secs,
        "eta_secs": snapshot.eta_secs,
    }


@router.get("/api/index/jobs")
async def jobs(state: AppState = Depends(get_state)) -> list[dict]:
    return await list_jobs(state, limit=20)


@router.get("/api/index/jobs/{job_id}/errors")
async def job_errors(
    job_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    state: AppState = Depends(get_state),
) -> list[dict]:
    return await list_job_errors(state, job_id, limit=limit)
