"""Ingest pipeline: scan folders, detect format, parse records, stream into index."""
from .format_detection import detect_format, RecordFormat
from .parser import parse_line
from .scanner import scan_folder, ScannedFile
from .csv_parser import extract_entities as extract_csv_entities
from .sql_dump import extract_entities as extract_sql_entities
from .stealer_logs import extract_entities as extract_stealer_entities
from .index_job import start_indexing, cancel_indexing, list_jobs, get_current_job

__all__ = [
    "RecordFormat",
    "detect_format",
    "parse_line",
    "scan_folder",
    "ScannedFile",
    "extract_csv_entities",
    "extract_sql_entities",
    "extract_stealer_entities",
    "start_indexing",
    "cancel_indexing",
    "list_jobs",
    "get_current_job",
]
