"""Batch-write parsed records into SQLite FTS5 + structured records table."""
from __future__ import annotations

from pathlib import Path
from typing import List

from breachelens.ingest.parser import ParsedRecord
from breachelens.state import AppState


async def write_batch(
    state: AppState,
    batch: List[ParsedRecord],
    source_id: int,
    file_path: Path,
    format_str: str,
) -> int:
    """Write a batch of parsed records. Returns the number of records written."""
    if not batch:
        return 0

    file_path_str = str(file_path)
    file_name = file_path.name
    extension = file_path.suffix.lower().lstrip(".")

    fts_rows: list[tuple] = []
    records_rows: list[tuple] = []

    for r in batch:
        primary_url = r.entities.urls[0] if r.entities.urls else None
        primary_email = r.entities.emails[0] if r.entities.emails else None
        primary_username = r.entities.usernames[0] if r.entities.usernames else None
        primary_hash = r.entities.hashes[0].value if r.entities.hashes else None
        primary_ip = (r.entities.ipv4s[0] if r.entities.ipv4s else
                      (r.entities.ipv6s[0] if r.entities.ipv6s else None))
        primary_phone = r.entities.phones[0] if r.entities.phones else None
        primary_secret = r.entities.secrets[0].kind if r.entities.secrets else None
        primary_email_domain = r.entities.email_domains[0] if r.entities.email_domains else None

        normalized_url = primary_url.normalized if primary_url else None
        path = primary_url.path if primary_url else None
        host = primary_url.host if primary_url else None
        root_domain = primary_url.root_domain if primary_url else None
        subdomain = primary_url.subdomain if primary_url else None
        endpoint_type = primary_url.endpoint_type if primary_url else None
        service_name = primary_url.service_name if primary_url else None

        fts_rows.append((
            r.searchable_text,
            source_id,
            None,  # file_id (not used)
            file_path_str,
            file_name,
            extension,
            r.line_number,
            r.byte_offset,
            r.byte_length,
            format_str,
            service_name,
            root_domain,
            host,
            subdomain,
            normalized_url,
            path,
            endpoint_type,
            primary_email,
            primary_email_domain,
            primary_username,
            primary_ip,
            primary_phone,
            primary_hash,
            primary_secret,
            r.dedupe.record_hash,
            r.dedupe.account_hash,
            r.dedupe.url_hash,
        ))

        records_rows.append((
            None,  # fts_rowid (filled in after FTS insert)
            source_id,
            None,
            file_path_str,
            file_name,
            extension,
            r.line_number,
            r.byte_offset,
            r.byte_length,
            format_str,
            service_name,
            root_domain,
            host,
            subdomain,
            normalized_url,
            path,
            endpoint_type,
            primary_email,
            primary_email_domain,
            primary_username,
            primary_ip,
            primary_phone,
            primary_hash,
            primary_secret,
            r.searchable_text,
            r.dedupe.record_hash,
            r.dedupe.account_hash,
            r.dedupe.url_hash,
        ))

    # Insert into FTS5 first to get rowids, then into structured records table.
    # Both inserts run inside the db lock (serialised writes).
    fts_sql = """
        INSERT INTO records_fts (
            searchable_text, source_id, file_id, file_path, file_name, extension,
            line_number, byte_offset, byte_length, record_format,
            service_name, root_domain, host, subdomain, normalized_url, path, endpoint_type,
            email, email_domain, username, ip, phone, hash, detected_secret_type,
            record_hash, account_hash, url_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    records_sql = """
        INSERT INTO records (
            fts_rowid, source_id, file_id, file_path, file_name, extension,
            line_number, byte_offset, byte_length, record_format,
            service_name, root_domain, host, subdomain, normalized_url, path, endpoint_type,
            email, email_domain, username, ip, phone, hash, detected_secret_type,
            searchable_text, record_hash, account_hash, url_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    async with state.db._lock:
        fts_rowids: list[int] = []
        for row in fts_rows:
            cur = await state.db.conn.execute(fts_sql, row)
            fts_rowids.append(cur.lastrowid)
        for i, row in enumerate(records_rows):
            row_list = list(row)
            row_list[0] = fts_rowids[i]
            await state.db.conn.execute(records_sql, tuple(row_list))
        await state.db.conn.commit()

    return len(batch)
