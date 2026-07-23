"""Identity profile endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from breachelens.errors import NotFoundError
from breachelens.identities import get_profile, list_profiles, rebuild_identities
from breachelens.state import AppState
from .auth import get_state, require_session

router = APIRouter(tags=["profiles"], dependencies=[Depends(require_session)])


@router.get("/api/profiles")
async def profiles(
    query: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    state: AppState = Depends(get_state),
) -> dict:
    return await list_profiles(state.db, query=query, page=page, page_size=page_size)


@router.get("/api/profiles/{profile_id}")
async def profile(profile_id: int, state: AppState = Depends(get_state)) -> dict:
    result = await get_profile(state.db, profile_id)
    if result is None:
        raise NotFoundError("profile not found")
    return result


@router.post("/api/profiles/rebuild")
async def rebuild(state: AppState = Depends(get_state)) -> dict:
    await rebuild_identities(state.db)
    count = await state.db.fetchval("SELECT COUNT(*) FROM identities") or 0
    return {"rebuilt": True, "profiles": int(count)}
