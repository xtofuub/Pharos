"""Reveal endpoint -- reads the original line from disk using byte offset."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from breachelens.errors import ForbiddenError, BadRequestError, NotFoundError, PathNotAllowedError
from breachelens.security.audit import AuditLogger
from breachelens.state import AppState
from .auth import get_state, require_session, SessionInfo

router = APIRouter(tags=["results"], dependencies=[Depends(require_session)])


class RevealRequest(BaseModel):
    confirm: bool
    source_file: str
    line_number: int
    byte_offset: int
    byte_length: int


@router.post("/api/results/{record_id}/reveal")
async def reveal(
    record_id: str,
    body: RevealRequest,
    session: SessionInfo = Depends(require_session),
    state: AppState = Depends(get_state),
) -> dict:
    if not state.config.auth.allow_reveal:
        raise ForbiddenError("reveal is disabled in settings")
    if not body.confirm:
        raise BadRequestError("must set confirm=true to reveal")

    # Validate the source file is within an indexed source
    p = Path(body.source_file)
    try:
        canonical = p.resolve(strict=True)
    except FileNotFoundError:
        raise NotFoundError("source file not found")

    sources = await state.db.fetchall("SELECT path FROM sources")
    allowed = any(str(canonical).startswith(str(Path(s["path"]).resolve())) for s in sources)
    if not allowed:
        raise PathNotAllowedError(f"file not within any indexed source: {body.source_file}")

    # Read the original line from disk
    def _read():
        with open(canonical, "rb") as fh:
            fh.seek(body.byte_offset)
            return fh.read(body.byte_length)

    raw_bytes = await asyncio.to_thread(_read)
    raw_line = raw_bytes.decode("utf-8", errors="replace").rstrip("\r\n")

    # Audit-log the reveal (never the raw value)
    audit = AuditLogger(state.db)
    await audit.log_reveal(
        user=session.username,
        record_id=record_id,
        source_file=str(canonical),
        line_number=body.line_number,
    )

    return {"raw_line": raw_line, "audit_recorded": True}
