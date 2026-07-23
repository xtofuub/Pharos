"""Search query builder and executor for SQLite FTS5 + structured records table."""
from __future__ import annotations

import re
import time
from typing import List, Optional

from breachelens.db import Database
from breachelens.entities.dedupe import query_hash  # noqa: F401 (re-exported)
from breachelens.errors import BadRequestError, RegexRejectedError, SearchError
from breachelens.security.masking import mask_preview

CATASTROPHIC_PATTERNS = ["(a+)+", "(a*)*", "(.+)+", ".*.*.*.*.*.*"]


class SearchRequest:
    def __init__(
        self,
        query: str,
        mode: str = "smart",
        query_type: str = "auto",
        filters: Optional[dict] = None,
        dedupe: str = "none",
        page: int = 1,
        page_size: int = 50,
        sort: str = "relevance",
    ) -> None:
        self.query = query
        self.mode = mode
        self.query_type = query_type
        self.filters = filters or {}
        self.dedupe = dedupe
        self.page = max(1, page)
        self.page_size = max(1, min(500, page_size))
        self.sort = sort


def detect_query_type(q: str) -> str:
    s = q.strip()
    if not s:
        return "text"
    if re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", s):
        return "email"
    if re.match(r"^(\d{1,3}\.){3}\d{1,3}$", s):
        return "ip"
    if re.match(r"^[a-fA-F0-9]{16,128}$", s):
        return "hash"
    if s.startswith(("http://", "https://")):
        return "url"
    if re.match(r"^[a-z0-9-]+\.[a-z]{2,}", s, re.IGNORECASE):
        return "domain"
    return "text"


def _validate_regex(pattern: str, max_length: int = 256) -> None:
    if len(pattern) > max_length:
        raise RegexRejectedError(f"pattern exceeds max length ({max_length} chars)")
    try:
        re.compile(pattern)
    except re.error as e:
        raise RegexRejectedError(f"invalid regex: {e}")
    for c in CATASTROPHIC_PATTERNS:
        if c in pattern:
            raise RegexRejectedError(f"catastrophic backtracking pattern detected: {c}")


def _field_for_query_type(qt: str) -> str:
    return {
        "email": "email",
        "username": "username",
        "domain": "root_domain",
        "service": "service_name",
        "url": "normalized_url",
        "ip": "ip",
        "phone": "phone",
        "hash": "hash",
        "text": "searchable_text",
        "auto": "searchable_text",
    }.get(qt, "searchable_text")


async def execute_search(db: Database, req: SearchRequest) -> dict:
    """Execute a search against FTS5 + structured records table."""
    started = time.monotonic()

    # Determine effective query type
    qt = req.query_type
    if qt == "auto":
        qt = detect_query_type(req.query)

    page = req.page
    page_size = req.page_size
    offset = (page - 1) * page_size

    # Build the SQL query against the structured records table.
    # We use FTS5 only for the `contains` and `regex` and `fulltext` modes.
    # For exact and smart modes we use direct b-tree lookups on indexed columns.
    where_clauses: List[str] = []
    params: list = []

    mode = req.mode
    query = req.query

    if mode == "regex":
        pattern = query if query.startswith("^") else f".*{re.escape(query)}.*"
        _validate_regex(pattern)
        # We can't do regex in SQLite easily; fall back to LIKE with wildcards
        where_clauses.append("searchable_text LIKE ?")
        params.append(f"%{query}%")
    elif mode == "exact":
        field = _field_for_query_type(qt)
        where_clauses.append(f"{field} = ?")
        params.append(query)
    elif mode == "contains":
        where_clauses.append("searchable_text LIKE ?")
        params.append(f"%{query}%")
    elif mode == "fulltext":
        # Use FTS5 MATCH
        # Escape special FTS5 chars
        escaped = re.sub(r'[":*\-\(\)]', " ", query).strip()
        where_clauses.append("rowid IN (SELECT rowid FROM records_fts WHERE records_fts MATCH ?)")
        params.append(escaped)
    else:  # smart
        # Try exact field match first, plus a LIKE fallback
        field = _field_for_query_type(qt)
        where_clauses.append(f"({field} = ? OR searchable_text LIKE ?)")
        params.append(query)
        params.append(f"%{query}%")

    # Apply filters
    f = req.filters
    if f.get("service_name"):
        where_clauses.append("service_name = ?")
        params.append(f["service_name"])
    if f.get("root_domain"):
        where_clauses.append("root_domain = ?")
        params.append(f["root_domain"])
    if f.get("host"):
        where_clauses.append("host = ?")
        params.append(f["host"])
    if f.get("endpoint_type"):
        where_clauses.append("endpoint_type = ?")
        params.append(f["endpoint_type"])
    if f.get("extension"):
        where_clauses.append("extension = ?")
        params.append(f["extension"])
    if f.get("record_format"):
        where_clauses.append("record_format = ?")
        params.append(f["record_format"])
    if f.get("source_id"):
        where_clauses.append("source_id = ?")
        params.append(int(f["source_id"]))

    # Dedupe
    if req.dedupe == "account":
        where_clauses.append("id IN (SELECT MIN(id) FROM records GROUP BY account_hash)")
    elif req.dedupe == "url":
        where_clauses.append("id IN (SELECT MIN(id) FROM records GROUP BY url_hash)")
    elif req.dedupe == "service_account":
        where_clauses.append("id IN (SELECT MIN(id) FROM records GROUP BY service_account_hash)")

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Sort
    sort_map = {
        "relevance": "id DESC",
        "newest": "created_at DESC",
        "file_path": "file_path ASC",
        "line_number": "line_number ASC",
        "service": "service_name ASC",
        "domain": "root_domain ASC",
    }
    order_sql = sort_map.get(req.sort, "id DESC")

    # Count total
    count_sql = f"SELECT COUNT(*) FROM records WHERE {where_sql}"
    total_row = await db.fetchone(count_sql, params)
    total = total_row[0] if total_row else 0

    # Fetch page
    list_sql = f"""
        SELECT id, source_id, file_path, file_name, extension, line_number, byte_offset, byte_length,
               record_format, service_name, root_domain, host, endpoint_type,
               email, username, normalized_url, searchable_text
        FROM records
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    rows = await db.fetchall(list_sql, params + [page_size, offset])

    results = []
    for r in rows:
        d = dict(r)
        searchable = d.get("searchable_text", "")
        masked = mask_preview(searchable, query)
        detected = []
        for field in ("email", "username", "hash", "ip", "phone", "normalized_url"):
            if d.get(field):
                detected.append(field)
        if d.get("record_format"):
            detected.append(d["record_format"])
        results.append({
            "id": f"rec_{d['id']}",
            "masked_preview": masked,
            "source_file": d.get("file_path", ""),
            "file_name": d.get("file_name", ""),
            "line_number": d.get("line_number", 0),
            "byte_offset": d.get("byte_offset", 0),
            "byte_length": d.get("byte_length", 0),
            "detected_fields": detected,
            "service_name": d.get("service_name"),
            "root_domain": d.get("root_domain"),
            "host": d.get("host"),
            "endpoint_type": d.get("endpoint_type"),
            "email": d.get("email"),
            "username": d.get("username"),
            "record_format": d.get("record_format", "unknown"),
            "confidence": 0.95 if qt in ("email", "username", "hash", "ip") else (0.85 if qt in ("domain", "url", "service") else 0.65),
            "reveal_available": True,
        })

    duration_ms = int((time.monotonic() - started) * 1000)

    # Service summary
    service_summary: dict[str, dict] = {}
    for r in results:
        svc = r.get("service_name") or "Unknown"
        if svc not in service_summary:
            service_summary[svc] = {"service_name": svc, "record_count": 0, "root_domains": []}
        service_summary[svc]["record_count"] += 1
        if r.get("root_domain") and r["root_domain"] not in service_summary[svc]["root_domains"]:
            service_summary[svc]["root_domains"].append(r["root_domain"])

    return {
        "results": results,
        "total": total,
        "search_duration_ms": duration_ms,
        "detected_query_type": qt,
        "page": page,
        "page_size": page_size,
        "service_summary": list(service_summary.values()),
    }
