"""Search endpoint."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from breachelens.index.query import SearchRequest, execute_search
from breachelens.security.audit import AuditLogger
from breachelens.security.validation import sanitize_query, validate_regex
from breachelens.state import AppState
from .auth import get_state, require_session, SessionInfo

router = APIRouter(tags=["search"], dependencies=[Depends(require_session)])


class SearchFilters(BaseModel):
    service_name: Optional[str] = None
    root_domain: Optional[str] = None
    host: Optional[str] = None
    endpoint_type: Optional[str] = None
    source_id: Optional[int] = None
    file_id: Optional[int] = None
    extension: Optional[str] = None
    file_name: Optional[str] = None
    path_contains: Optional[str] = None
    indexed_after: Optional[str] = None
    indexed_before: Optional[str] = None
    record_format: Optional[str] = None


class SearchRequestBody(BaseModel):
    query: str
    mode: str = "smart"
    query_type: str = "auto"
    filters: Optional[SearchFilters] = None
    dedupe: str = "none"
    page: int = 1
    page_size: int = 50
    sort: str = "relevance"


@router.post("/api/search")
async def search(
    body: SearchRequestBody,
    session: SessionInfo = Depends(require_session),
    state: AppState = Depends(get_state),
) -> dict:
    clean_query = sanitize_query(body.query)
    if body.mode == "regex":
        validate_regex(clean_query, state.config.regex_safety.max_pattern_length)

    req = SearchRequest(
        query=clean_query,
        mode=body.mode,
        query_type=body.query_type,
        filters=body.filters.model_dump() if body.filters else {},
        dedupe=body.dedupe,
        page=body.page,
        page_size=body.page_size,
        sort=body.sort,
    )
    response = await execute_search(state.db, req)

    # Audit log (query hash only, never raw query)
    filters_used = [k for k, v in (body.filters.model_dump() if body.filters else {}).items() if v]
    audit = AuditLogger(state.db)
    await audit.log_search(
        user=session.username,
        query=clean_query,
        query_type=response["detected_query_type"],
        filters_used=filters_used,
        result_count=response["total"],
    )

    return response
