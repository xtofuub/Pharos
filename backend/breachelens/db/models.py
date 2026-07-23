"""Pydantic models for DB rows and API responses."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class Source(BaseModel):
    id: int
    path: str
    display_name: Optional[str] = None
    storage_mode: str
    allowed_extensions: str
    status: str
    files_count: int
    records_count: int
    size_bytes: int
    last_indexed_at: Optional[str] = None
    created_at: str


class FileRecord(BaseModel):
    id: int
    source_id: int
    path: str
    file_name: str
    extension: str
    size_bytes: int
    line_count: int
    records_indexed: int
    mtime: int
    detected_format: Optional[str] = None
    last_indexed_at: Optional[str] = None
    status: str


class IndexJob(BaseModel):
    id: int
    source_id: Optional[int] = None
    status: str
    started_at: str
    finished_at: Optional[str] = None
    files_total: int
    files_processed: int
    files_skipped: int
    records_indexed: int
    errors_count: int
    throughput_lps: float
    throughput_mbs: float
    current_file: Optional[str] = None
    error_message: Optional[str] = None


class IndexError(BaseModel):
    id: int
    job_id: int
    file_path: str
    line_number: Optional[int] = None
    message: str
    severity: str
    timestamp: str


class AuditEntry(BaseModel):
    id: int
    timestamp: str
    user: str
    action: str
    query_hash: Optional[str] = None
    query_type: Optional[str] = None
    filters_used: Optional[str] = None
    result_count: int
    reveal_event: bool
    source_id: Optional[int] = None
    source_ip: Optional[str] = None


class SearchResult(BaseModel):
    id: str
    masked_preview: str
    source_file: str
    file_name: str
    line_number: int
    byte_offset: int
    byte_length: int
    detected_fields: List[str]
    service_name: Optional[str] = None
    root_domain: Optional[str] = None
    host: Optional[str] = None
    endpoint_type: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    record_format: str
    confidence: float
    reveal_available: bool


class ServiceSummary(BaseModel):
    service_name: str
    record_count: int
    root_domains: List[str]


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    search_duration_ms: int
    detected_query_type: str
    page: int
    page_size: int
    service_summary: List[ServiceSummary]


class Stats(BaseModel):
    total_records: int
    total_files: int
    total_sources: int
    total_size_bytes: int
    last_indexing_job: Optional[str] = None


class JobSnapshot(BaseModel):
    job_id: int
    source_id: int
    status: str
    started_at: str
    current_file: Optional[str] = None
    files_total: int
    files_processed: int
    files_skipped: int
    records_indexed: int
    errors: int
    lines_per_sec: float
    mb_per_sec: float
    elapsed_secs: float
    eta_secs: Optional[float] = None
