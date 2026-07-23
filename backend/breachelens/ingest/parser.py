"""Line parser: turn a raw line into a ParsedRecord ready for indexing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from breachelens.entities import (
    ExtractedEntities,
    compute_hashes,
    extract as extract_entities,
)
from breachelens.entities.url_normalizer import normalize as normalize_url
from breachelens.ingest.csv_parser import extract_entities as extract_csv_entities
from breachelens.ingest.format_detection import RecordFormat
from breachelens.ingest.sql_dump import extract_entities as extract_sql_entities
from breachelens.ingest.stealer_logs import extract_entities as extract_stealer_entities


@dataclass
class ParsedRecord:
    line_number: int
    byte_offset: int
    byte_length: int
    raw_line: str
    format: RecordFormat
    searchable_text: str
    entities: ExtractedEntities
    dedupe: "DedupeHashesView"


@dataclass
class DedupeHashesView:
    record_hash: str
    account_hash: Optional[str]
    url_hash: Optional[str]
    service_account_hash: Optional[str]


def parse_line(
    line: str,
    line_number: int,
    byte_offset: int,
    format: RecordFormat,
    byte_length: int | None = None,
) -> ParsedRecord:
    """Parse a single line into a ParsedRecord."""
    byte_length = byte_length if byte_length is not None else len(line.encode("utf-8"))
    raw_line = line

    if format in (RecordFormat.CSV, RecordFormat.TSV):
        entities = extract_csv_entities(line, format)
    elif format == RecordFormat.JSONL:
        entities = _extract_jsonl(line)
    elif format == RecordFormat.SQL_DUMP:
        entities = extract_sql_entities(line)
    elif format == RecordFormat.STEALER_LOG:
        entities = extract_stealer_entities(line)
    elif format == RecordFormat.COMBO:
        entities = _extract_combo(line)
    elif format == RecordFormat.BROWSER_EXPORT:
        entities = _extract_browser_export(line)
    else:
        entities = extract_entities(line)

    searchable = entities.merge_into_searchable_text(raw_line)
    primary_url = entities.urls[0] if entities.urls else None
    primary_email = entities.emails[0] if entities.emails else None
    primary_username = entities.usernames[0] if entities.usernames else None
    primary_service = primary_url.service_name if primary_url else None
    primary_url_str = primary_url.normalized if primary_url else None

    hashes = compute_hashes(
        raw_line=raw_line,
        service_name=primary_service,
        email=primary_email,
        username=primary_username,
        normalized_url=primary_url_str,
    )

    return ParsedRecord(
        line_number=line_number,
        byte_offset=byte_offset,
        byte_length=byte_length,
        raw_line=raw_line,
        format=format,
        searchable_text=searchable,
        entities=entities,
        dedupe=DedupeHashesView(
            record_hash=hashes.record_hash,
            account_hash=hashes.account_hash,
            url_hash=hashes.url_hash,
            service_account_hash=hashes.service_account_hash,
        ),
    )


def _extract_jsonl(line: str) -> ExtractedEntities:
    import json

    out = ExtractedEntities()
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return extract_entities(line)
    if isinstance(obj, dict):
        _collect_json(obj, out)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                _collect_json(item, out)
    return out


def _collect_json(obj: dict, out: ExtractedEntities) -> None:
    for key, val in obj.items():
        lower_k = key.lower()
        if isinstance(val, str):
            if lower_k in ("email", "mail"):
                out.emails.append(val.lower())
                if "@" in val:
                    out.email_domains.append(val.split("@", 1)[1])
            elif lower_k in ("username", "user", "login"):
                out.usernames.append(val)
            elif lower_k in ("password", "pass", "pwd"):
                out.possible_passwords.append(val)
            elif lower_k in ("url", "website"):
                normalized = normalize_url(val)
                if normalized is not None:
                    out.urls.append(normalized)
            else:
                sub = extract_entities(val)
                _merge(out, sub)
        elif isinstance(val, dict):
            _collect_json(val, out)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    _collect_json(item, out)
                elif isinstance(item, str):
                    sub = extract_entities(item)
                    _merge(out, sub)


def _extract_combo(line: str) -> ExtractedEntities:
    parts = line.split(":", 3)
    if len(parts) < 2:
        return extract_entities(line)
    out = extract_entities(line)
    if len(parts) == 2:
        if parts[0].lower() not in {e for e in out.emails} and parts[0] not in out.usernames:
            out.usernames.append(parts[0])
        out.possible_passwords.append(parts[1])
    elif len(parts) >= 3:
        normalized = normalize_url(parts[0])
        if normalized is not None and not any(u.normalized == normalized.normalized for u in out.urls):
            out.urls.append(normalized)
        out.usernames.append(parts[1])
        out.possible_passwords.append(parts[2])
    return out


def _extract_browser_export(line: str) -> ExtractedEntities:
    parts = line.split("\t")
    if len(parts) < 2:
        return extract_entities(line)
    out = ExtractedEntities()
    normalized = normalize_url(parts[0])
    if normalized is not None:
        out.urls.append(normalized)
    out.usernames.append(parts[1])
    if len(parts) >= 3:
        out.possible_passwords.append(parts[2])
    return out


def _merge(into: ExtractedEntities, frm: ExtractedEntities) -> None:
    into.urls.extend(frm.urls)
    into.emails.extend(frm.emails)
    into.email_domains.extend(frm.email_domains)
    into.usernames.extend(frm.usernames)
    into.phones.extend(frm.phones)
    into.ipv4s.extend(frm.ipv4s)
    into.ipv6s.extend(frm.ipv6s)
    into.hashes.extend(frm.hashes)
    into.secrets.extend(frm.secrets)
    into.possible_passwords.extend(frm.possible_passwords)
