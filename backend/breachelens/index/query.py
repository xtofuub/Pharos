"""Ranked SQLite FTS5, exact, contains, and real regex search."""
from __future__ import annotations

import re
import time
from typing import List, Optional

from breachelens.db import Database
from breachelens.errors import BadRequestError, RegexRejectedError
from breachelens.security.masking import mask_preview

CATASTROPHIC_PATTERNS = ["(a+)+", "(a*)*", "(.+)+", ".*.*.*.*.*.*"]
ALLOWED_MODES = {"smart", "exact", "contains", "fulltext", "regex"}


class SearchRequest:
    def __init__(self, query: str, mode: str = "smart", query_type: str = "auto",
                 filters: Optional[dict] = None, dedupe: str = "none", page: int = 1,
                 page_size: int = 50, sort: str = "relevance", max_results: int = 1000) -> None:
        if mode not in ALLOWED_MODES:
            raise BadRequestError(f"unsupported search mode: {mode}")
        self.query = query
        self.mode = mode
        self.query_type = query_type
        self.filters = filters or {}
        self.dedupe = dedupe
        self.page = max(1, page)
        self.page_size = max(1, min(500, page_size))
        self.sort = sort
        self.max_results = max(1, min(10_000, max_results))


def detect_query_type(q: str) -> str:
    value = q.strip()
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value): return "email"
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", value): return "ip"
    if re.fullmatch(r"[a-fA-F0-9]{16,128}", value): return "hash"
    if value.startswith(("http://", "https://")): return "url"
    if re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", value, re.I): return "domain"
    return "text"


def _validate_regex(pattern: str, max_length: int = 256) -> None:
    if len(pattern) > max_length:
        raise RegexRejectedError(f"pattern exceeds max length ({max_length} chars)")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise RegexRejectedError(f"invalid regex: {exc}")
    for candidate in CATASTROPHIC_PATTERNS:
        if candidate in pattern:
            raise RegexRejectedError(f"catastrophic backtracking pattern detected: {candidate}")


def _field_for_query_type(query_type: str) -> str:
    return {"email":"email","username":"username","domain":"root_domain","service":"service_name",
            "url":"normalized_url","ip":"ip","phone":"phone","hash":"hash","text":"searchable_text"}.get(query_type,"searchable_text")


def _fts_query(query: str) -> str:
    tokens = [token for token in re.sub(r'[^\w@.+-]+', ' ', query, flags=re.UNICODE).split() if token]
    if not tokens: return '""'
    return " AND ".join(f'"{token.replace(chr(34), "")}"*' for token in tokens[:12])


def _filters(filters: dict, alias: str = "r") -> tuple[list[str], list[object]]:
    clauses, params = [], []
    mapping = {"service_name":"service_name","root_domain":"root_domain","host":"host",
               "endpoint_type":"endpoint_type","extension":"extension","record_format":"record_format",
               "source_id":"source_id","file_id":"file_id","file_name":"file_name"}
    for key, column in mapping.items():
        value = filters.get(key)
        if value not in (None, ""):
            clauses.append(f"{alias}.{column} = ?")
            params.append(int(value) if key in {"source_id","file_id"} else value)
    if filters.get("path_contains"):
        clauses.append(f"{alias}.file_path LIKE ?"); params.append(f"%{filters['path_contains']}%")
    if filters.get("indexed_after"):
        clauses.append(f"{alias}.created_at >= ?"); params.append(filters["indexed_after"])
    if filters.get("indexed_before"):
        clauses.append(f"{alias}.created_at <= ?"); params.append(filters["indexed_before"])
    return clauses, params


async def execute_search(db: Database, req: SearchRequest) -> dict:
    started = time.monotonic()
    query_type = detect_query_type(req.query) if req.query_type == "auto" else req.query_type
    field = _field_for_query_type(query_type)
    filter_clauses, filter_params = _filters(req.filters)
    where, params, joins, relevance = list(filter_clauses), list(filter_params), "", "r.id DESC"

    if req.mode == "regex":
        _validate_regex(req.query); where.insert(0, "REGEXP(?, r.searchable_text)"); params.insert(0, req.query)
    elif req.mode == "exact":
        where.insert(0, f"r.{field} = ?"); params.insert(0, req.query)
    elif req.mode == "contains":
        where.insert(0, "r.searchable_text LIKE ?"); params.insert(0, f"%{req.query}%")
    elif req.mode == "fulltext" or (req.mode == "smart" and query_type == "text"):
        joins = "JOIN records_fts ON records_fts.rowid = r.fts_rowid"
        where.insert(0, "records_fts MATCH ?"); params.insert(0, _fts_query(req.query))
        relevance = "bm25(records_fts) ASC, r.id DESC"
    else:
        where.insert(0, f"(r.{field} = ? OR r.searchable_text LIKE ?)")
        params = [req.query, f"%{req.query}%", *filter_params]
        relevance = f"CASE WHEN r.{field} = ? THEN 0 ELSE 1 END, r.id DESC"

    if req.dedupe == "account": where.append("r.id IN (SELECT MIN(id) FROM records GROUP BY account_hash)")
    elif req.dedupe == "url": where.append("r.id IN (SELECT MIN(id) FROM records GROUP BY url_hash)")
    elif req.dedupe == "service_account": where.append("r.id IN (SELECT MIN(id) FROM records GROUP BY service_name, account_hash)")

    where_sql = " AND ".join(where) if where else "1=1"
    sort_map = {"relevance":relevance,"newest":"r.created_at DESC","file_path":"r.file_path ASC, r.line_number ASC",
                "line_number":"r.line_number ASC","service":"r.service_name ASC","domain":"r.root_domain ASC"}
    order_sql = sort_map.get(req.sort, relevance)
    list_params, count_params = list(params), list(params)
    if req.mode == "smart" and query_type != "text" and order_sql == relevance: list_params.append(req.query)

    count_limit = req.max_results + 1
    count_sql = f"SELECT COUNT(*) FROM (SELECT 1 FROM records r {joins} WHERE {where_sql} LIMIT {count_limit})"
    total = int(await db.fetchval(count_sql, count_params) or 0)
    truncated = total > req.max_results; total = min(total, req.max_results)
    offset = (req.page - 1) * req.page_size
    list_sql = f"""
        SELECT r.id, r.source_id, r.file_id, r.file_path, r.file_name, r.extension,
               r.line_number, r.byte_offset, r.byte_length, r.record_format,
               r.service_name, r.root_domain, r.host, r.endpoint_type,
               r.email, r.username, r.normalized_url, r.searchable_text,
               (SELECT identity_id FROM identity_records ir WHERE ir.record_id=r.id LIMIT 1) AS identity_id
        FROM records r {joins} WHERE {where_sql}
        ORDER BY {order_sql} LIMIT ? OFFSET ?
    """
    rows = await db.fetchall(list_sql, [*list_params, req.page_size, offset])
    results = []
    for row in rows:
        item = dict(row)
        entity_rows = await db.fetchall("SELECT DISTINCT entity_type FROM record_entities WHERE record_id=? ORDER BY entity_type",(item["id"],))
        results.append({"id":f"rec_{item['id']}","masked_preview":mask_preview(item.get("searchable_text") or "",req.query),
            "source_file":item.get("file_path") or "","file_name":item.get("file_name") or "","line_number":item.get("line_number") or 0,
            "byte_offset":item.get("byte_offset") or 0,"byte_length":item.get("byte_length") or 0,
            "detected_fields":[entity[0] for entity in entity_rows],"service_name":item.get("service_name"),
            "root_domain":item.get("root_domain"),"host":item.get("host"),"endpoint_type":item.get("endpoint_type"),
            "email":item.get("email"),"username":item.get("username"),"record_format":item.get("record_format") or "unknown",
            "identity_id":item.get("identity_id"),"confidence":0.98 if query_type in {"email","hash","ip"} else 0.88,
            "reveal_available":True})
    service_summary = {}
    for item in results:
        service = item.get("service_name") or "Unknown"
        bucket = service_summary.setdefault(service,{"service_name":service,"record_count":0,"root_domains":[]})
        bucket["record_count"] += 1
        domain = item.get("root_domain")
        if domain and domain not in bucket["root_domains"]: bucket["root_domains"].append(domain)
    return {"results":results,"total":total,"truncated":truncated,
            "search_duration_ms":int((time.monotonic()-started)*1000),"detected_query_type":query_type,
            "page":req.page,"page_size":req.page_size,"service_summary":list(service_summary.values())}
