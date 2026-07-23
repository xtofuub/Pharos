"""Source folder management and local scan-preview endpoints."""
from __future__ import annotations

import asyncio
import os
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from breachelens.errors import BadRequestError, ForbiddenError
from breachelens.ingest.index_job import start_indexing
from breachelens.ingest.scanner import scan_folder_detailed
from breachelens.security.validation import validate_source_folder
from breachelens.state import AppState
from .auth import SessionInfo, get_state, require_session

router = APIRouter(tags=["sources"], dependencies=[Depends(require_session)])
DEFAULT_EXTENSIONS = ".txt,.csv,.tsv,.log,.jsonl,.sql"

class AddSourceRequest(BaseModel):
    path: str
    display_name: Optional[str] = None
    storage_mode: Optional[str] = None
    allowed_extensions: Optional[str] = None
    authorized: bool = False
    auto_index: bool = True

class SourceResponse(BaseModel):
    id: int; path: str; display_name: Optional[str] = None; storage_mode: str
    allowed_extensions: str; status: str; files_count: int; records_count: int
    size_bytes: int; last_indexed_at: Optional[str] = None; created_at: str

def _extensions(value: str | None) -> list[str]:
    return [item.strip().lstrip(".").lower() for item in (value or DEFAULT_EXTENSIONS).split(",") if item.strip()]

@router.get("/api/sources", response_model=List[SourceResponse])
async def list_sources(state: AppState = Depends(get_state)) -> List[SourceResponse]:
    rows = await state.db.fetchall("""SELECT id,path,display_name,storage_mode,allowed_extensions,status,
        files_count,records_count,size_bytes,last_indexed_at,created_at FROM sources ORDER BY id""")
    return [SourceResponse(**dict(row)) for row in rows]

@router.post("/api/sources/preview")
async def preview_source(req: AddSourceRequest) -> dict:
    canonical = validate_source_folder(req.path)
    result = await asyncio.to_thread(scan_folder_detailed, canonical, _extensions(req.allowed_extensions))
    return {"valid":True,"canonical_path":str(canonical),"files_count":len(result.files),"files_seen":result.files_seen,
        "directories_visited":result.directories_visited,"size_bytes":result.size_bytes,"errors_count":len(result.errors),
        "errors":result.errors[:20],"sample_files":[str(item.path) for item in result.files[:10]]}

@router.post("/api/sources/browse")
async def browse_source() -> dict:
    if os.name != "nt":
        return {"supported":False,"path":None,"message":"native folder picker is currently available on Windows"}
    def choose() -> str:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk(); root.withdraw(); root.attributes("-topmost",True)
        try: return filedialog.askdirectory(title="Choose a folder for Pharos to scan",mustexist=True) or ""
        finally: root.destroy()
    try: selected=await asyncio.to_thread(choose)
    except Exception as exc: return {"supported":False,"path":None,"message":f"folder picker failed: {exc}"}
    return {"supported":True,"path":selected or None}

@router.post("/api/sources", response_model=dict)
async def add_source(req:AddSourceRequest, session:SessionInfo=Depends(require_session), state:AppState=Depends(get_state))->dict:
    if not req.authorized: raise ForbiddenError("must confirm dataset authorization")
    canonical=validate_source_folder(req.path)
    storage_mode=req.storage_mode or state.config.storage.default_mode
    if storage_mode not in ("offset","full"): raise BadRequestError(f"invalid storage_mode: {storage_mode}")
    allowed_exts=req.allowed_extensions or DEFAULT_EXTENSIONS
    existing=await state.db.fetchone("SELECT id,status FROM sources WHERE path=?",(str(canonical),))
    if existing:
        source_id=int(existing["id"])
        await state.db.execute("UPDATE sources SET display_name=COALESCE(?,display_name),allowed_extensions=?,storage_mode=? WHERE id=?",
            (req.display_name,allowed_exts,storage_mode,source_id)); created=False
    else:
        cur=await state.db.execute("""INSERT INTO sources(path,display_name,storage_mode,allowed_extensions,status,authorized_by,authorized_at)
            VALUES(?,?,?,?,'pending',?,datetime('now'))""",(str(canonical),req.display_name,storage_mode,allowed_exts,session.username))
        source_id=int(cur.lastrowid or 0); created=True
    job_id=await start_indexing(state,source_id) if req.auto_index else None
    return {"id":source_id,"path":str(canonical),"status":"indexing" if job_id else "pending","job_id":job_id,"created":created}

@router.delete("/api/sources/{source_id}")
async def delete_source(source_id:int,state:AppState=Depends(get_state))->dict:
    await state.db.execute("DELETE FROM sources WHERE id=?",(source_id,)); return {"deleted":source_id}

@router.post("/api/sources/validate")
async def validate_source(req:AddSourceRequest)->dict:
    try:
        canonical=validate_source_folder(req.path); return {"valid":True,"canonical_path":str(canonical)}
    except Exception as exc: return {"valid":False,"error":str(exc)}
