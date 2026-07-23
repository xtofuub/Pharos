"""Record format detection by extension + content sniffing."""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path


class RecordFormat(str, Enum):
    PLAIN_TEXT = "plain_text"
    CSV = "csv"
    TSV = "tsv"
    JSONL = "jsonl"
    SQL_DUMP = "sql_dump"
    COMBO = "combo"
    STEALER_LOG = "stealer_log"
    BROWSER_EXPORT = "browser_export"
    MIXED = "mixed"


_COMBO_RE = re.compile(r"^[^:\s]+:[^:\s]+(:[^:\s]+){0,2}$")


def detect_format(path: Path, sample: bytes) -> RecordFormat:
    """Detect the most likely record format of a file."""
    ext = path.suffix.lower().lstrip(".")
    sample_text = sample.decode("utf-8", errors="replace")

    # Extension is a strong signal
    if ext == "csv":
        return RecordFormat.CSV
    if ext == "tsv":
        return RecordFormat.TSV
    if ext in ("jsonl", "ndjson"):
        return RecordFormat.JSONL
    if ext in ("sql", "dump", "psql"):
        return RecordFormat.SQL_DUMP
    if ext == "log":
        return _detect_content(sample_text) or RecordFormat.PLAIN_TEXT

    return _detect_content(sample_text) or RecordFormat.PLAIN_TEXT


def _detect_content(sample: str) -> RecordFormat | None:
    lower = sample.lower()
    # SQL dump
    if "insert into" in lower:
        return RecordFormat.SQL_DUMP
    # Stealer-log style: multiple labeled fields
    signals = ["url:", "username:", "password:", "login:", "pass:", "host:"]
    hits = sum(1 for s in signals if s in lower)
    if hits >= 2:
        return RecordFormat.STEALER_LOG
    # JSONL
    first_line = sample.split("\n", 1)[0].strip() if sample else ""
    if first_line.startswith("{"):
        return RecordFormat.JSONL
    # CSV vs TSV
    lines = [l for l in sample.split("\n")[:5] if l.strip()]
    if len(lines) >= 2:
        comma_count = sum(l.count(",") for l in lines)
        tab_count = sum(l.count("\t") for l in lines)
        if tab_count > comma_count and tab_count / len(lines) >= 2:
            return RecordFormat.TSV
        if comma_count > tab_count and comma_count / len(lines) >= 2:
            return RecordFormat.CSV
    # Combo
    combo_hits = sum(1 for l in lines[:10] if _COMBO_RE.match(l.strip()))
    if combo_hits >= 3:
        return RecordFormat.COMBO
    return None
