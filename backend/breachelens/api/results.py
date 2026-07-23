"""Secure reveal endpoint: all file coordinates come from trusted indexed metadata."""
from __future__ import annotations
import asyncio
from pathlib import Path
from fastapi import APIRouter,Depends
from pydantic import BaseModel
from breachelens.errors import BadRequestError,ForbiddenError,NotFoundError,PathNotAllowedError
from breachelens.security.audit import AuditLogger
from breachelens.security.validation import is_within
from breachelens.state import AppState
from .auth import SessionInfo,get_state,require_session
router=APIRouter(tags=["results"],dependencies=[Depends(require_session)])
class RevealRequest(BaseModel):confirm:bool

def _numeric_record_id(record_id:str)->int:
    value=record_id[4:] if record_id.startswith("rec_") else record_id
    if not value.isdigit():raise BadRequestError("invalid record id")
    return int(value)

@router.post("/api/results/{record_id}/reveal")
async def reveal(record_id:str,body:RevealRequest,session:SessionInfo=Depends(require_session),state:AppState=Depends(get_state))->dict:
    if not state.config.auth.allow_reveal:raise ForbiddenError("reveal is disabled in settings")
    if not body.confirm:raise BadRequestError("must set confirm=true to reveal")
    numeric_id=_numeric_record_id(record_id)
    row=await state.db.fetchone("""SELECT r.id,r.source_id,r.file_id,r.file_path,r.line_number,r.byte_offset,r.byte_length,
        f.size_bytes,f.mtime FROM records r LEFT JOIN files f ON f.id=r.file_id WHERE r.id=?""",(numeric_id,))
    if row is None:raise NotFoundError("record not found")
    path=Path(row["file_path"])
    try:canonical=path.resolve(strict=True)
    except FileNotFoundError:raise NotFoundError("source file no longer exists")
    source=await state.db.fetchone("SELECT path FROM sources WHERE id=?",(row["source_id"],))
    if source is None or not is_within(canonical,Path(source["path"])):raise PathNotAllowedError("record file is outside its indexed source")
    stat=canonical.stat()
    if row["mtime"] is not None and int(stat.st_mtime)!=int(row["mtime"]):raise BadRequestError("source file changed after indexing; re-index it before revealing")
    if row["size_bytes"] is not None and stat.st_size!=int(row["size_bytes"]):raise BadRequestError("source file size changed after indexing; re-index it before revealing")
    max_read=min(state.config.indexing.max_line_length*4,1024*1024)
    byte_length=max(0,min(int(row["byte_length"]),max_read))
    if byte_length==0:raise BadRequestError("record has an invalid byte length")
    def _read()->bytes:
        with open(canonical,"rb") as handle:
            handle.seek(int(row["byte_offset"]));return handle.read(byte_length)
    raw=await asyncio.to_thread(_read);raw_line=raw.decode("utf-8",errors="replace").rstrip("\r\n")
    audit=AuditLogger(state.db)
    await audit.log_reveal(user=session.username,record_id=f"rec_{numeric_id}",source_file=str(canonical),line_number=int(row["line_number"]))
    return {"raw_line":raw_line,"audit_recorded":True}
