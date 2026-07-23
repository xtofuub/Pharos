"""Health check."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from breachelens.state import AppState
from .auth import get_state

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(state: AppState = Depends(get_state)) -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "local_only": True,
        "bind": state.config.server.bind_addr,
    }
