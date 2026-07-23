"""Local maintenance operations: backup, reset, and data-folder access."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from breachelens.state import AppState
from .auth import get_state, require_session

router = APIRouter(tags=["maintenance"], dependencies=[Depends(require_session)])


@router.post("/api/maintenance/reset-index")
async def reset_index(state: AppState = Depends(get_state)) -> dict:
    async with state.db._lock:
        conn = state.db.conn
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await conn.execute("DELETE FROM identity_entities")
            await conn.execute("DELETE FROM identity_records")
            await conn.execute("DELETE FROM identities")
            await conn.execute("DELETE FROM record_entities")
            await conn.execute("DELETE FROM records")
            await conn.execute("DELETE FROM records_fts")
            await conn.execute("DELETE FROM files")
            await conn.execute("DELETE FROM index_errors")
            await conn.execute("DELETE FROM index_jobs")
            await conn.execute("UPDATE sources SET status='pending', files_count=0, records_count=0, size_bytes=0, last_indexed_at=NULL")
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return {"reset": True}


@router.get("/api/maintenance/backup")
async def backup_database(state: AppState = Depends(get_state)) -> FileResponse:
    backup_dir = state.config.storage.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"pharos-{stamp}.db"
    async with state.db._lock:
        await state.db.conn.execute("PRAGMA wal_checkpoint(FULL)")
        await state.db.conn.commit()
        await asyncio.to_thread(shutil.copy2, state.config.storage.db_path, destination)
    await state.db.execute("INSERT INTO app_backups(path, size_bytes) VALUES (?, ?)", (str(destination), destination.stat().st_size))
    return FileResponse(str(destination), filename=destination.name, media_type="application/octet-stream")


@router.post("/api/maintenance/open-data-folder")
async def open_data_folder(state: AppState = Depends(get_state)) -> dict:
    folder = state.config.storage.data_dir
    folder.mkdir(parents=True, exist_ok=True)
    def _open() -> None:
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    try:
        await asyncio.to_thread(_open)
        return {"opened": True, "path": str(folder)}
    except Exception as exc:
        return {"opened": False, "path": str(folder), "message": str(exc)}
