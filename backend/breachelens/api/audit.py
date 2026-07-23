"""Audit log endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from breachelens.security.audit import list_audit_entries
from breachelens.state import AppState
from .auth import get_state, require_session

router = APIRouter(tags=["audit"], dependencies=[Depends(require_session)])


@router.get("/api/audit")
async def audit(
    limit: int = Query(100, ge=1, le=1000),
    state: AppState = Depends(get_state),
) -> list[dict]:
    return await list_audit_entries(state.db, limit=limit)
