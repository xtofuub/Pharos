"""Indexing control and diagnostics endpoints."""
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
async def start_index(source_id: int, force: bool = Query(False), state: AppState = Depends(get_state)) -> dict:
    job_id = await start_indexing(state, source_id, force=force)
    return {"job_id": job_id, "status": "running", "force": force}


@router.post("/api/index/cancel")
async def cancel(state: AppState = Depends(get_state)) -> dict:
    await cancel_indexing(state)
    return {"status": "cancelled"}


@router.get("/api/index/status")
async def status() -> dict | None:
    snap = get_current_job()
    if snap is None:
        return None
    return {
        "job_id": snap.job_id,
        "source_id": snap.source_id,
        "status": snap.status,
        "phase": snap.phase,
        "started_at": snap.started_at,
        "current_file": snap.current_file,
        "files_total": snap.files_total,
        "files_processed": snap.files_processed,
        "files_failed": snap.files_failed,
        "files_skipped": snap.files_skipped,
        "records_indexed": snap.records_indexed,
        "warnings": snap.warnings,
        "errors": snap.errors,
        "bytes_total": snap.bytes_total,
        "bytes_processed": snap.bytes_processed,
        "current_file_bytes": snap.current_file_bytes,
        "current_file_size": snap.current_file_size,
        "current_line": snap.current_line,
        "progress_percent": snap.progress_percent,
        "lines_per_sec": snap.lines_per_sec,
        "mb_per_sec": snap.mb_per_sec,
        "elapsed_secs": snap.elapsed_secs,
        "eta_secs": snap.eta_secs,
    }


@router.get("/api/index/jobs")
async def jobs(state: AppState = Depends(get_state)) -> list[dict]:
    return await list_jobs(state, limit=30)


@router.get("/api/index/jobs/{job_id}/errors")
async def job_errors(job_id: int, state: AppState = Depends(get_state)) -> list[dict]:
    return await list_job_errors(state, job_id)
