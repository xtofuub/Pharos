"""Batch-write parsed records, all extracted entities, and FTS rows."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from breachelens.identities import canonicalize_email
from breachelens.ingest.parser import ParsedRecord
from breachelens.state import AppState


def _norm(entity_type: str, value: str) -> str:
    value = value.strip()
    if entity_type == "email":
        return canonicalize_email(value)
    if entity_type in {"username", "domain", "host", "service", "ip", "hash", "secret_type", "email_domain"}:
        return value.casefold()
    if entity_type == "phone":
        digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        return digits or value.casefold()
    return value.casefold()


def iter_entities(record: ParsedRecord) -> Iterable[tuple[str, str, str | None, str | None]]:
    e = record.entities
    for email in e.emails:
        yield "email", email, None, email.split("@", 1)[1] if "@" in email else None
    for domain in e.email_domains:
        yield "email_domain", domain, None, domain
    for username in e.usernames:
        yield "username", username, None, None
    for phone in e.phones:
        yield "phone", phone, None, None
    for ip in [*e.ipv4s, *e.ipv6s]:
        yield "ip", ip, None, None
    for item in e.hashes:
        yield "hash", item.value, None, None
    for item in e.secrets:
        yield "secret_type", item.kind, None, None
    for url in e.urls:
        yield "url", url.normalized, url.service_name, url.root_domain
        if url.host:
            yield "host", url.host, url.service_name, url.root_domain
        if url.root_domain:
            yield "domain", url.root_domain, url.service_name, url.root_domain
        if url.service_name:
            yield "service", url.service_name, url.service_name, url.root_domain


async def write_batch(
    state: AppState,
    batch: List[ParsedRecord],
    source_id: int,
    file_id: int,
    file_path: Path,
    format_str: str,
) -> int:
    """Write one parsed batch atomically. Returns inserted record count."""
    if not batch:
        return 0

    file_path_str = str(file_path)
    file_name = file_path.name
    extension = file_path.suffix.lower().lstrip(".")
    inserted = 0

    fts_sql = """
        INSERT INTO records_fts (
            searchable_text, source_id, file_id, file_path, file_name, extension,
            line_number, byte_offset, byte_length, record_format,
            service_name, root_domain, host, subdomain, normalized_url, path, endpoint_type,
            email, email_domain, username, ip, phone, hash, detected_secret_type,
            record_hash, account_hash, url_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    record_sql = """
        INSERT INTO records (
            fts_rowid, source_id, file_id, file_path, file_name, extension,
            line_number, byte_offset, byte_length, record_format,
            service_name, root_domain, host, subdomain, normalized_url, path, endpoint_type,
            email, email_domain, username, ip, phone, hash, detected_secret_type,
            searchable_text, record_hash, account_hash, url_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    async with state.db._lock:
        conn = state.db.conn
        await conn.execute("BEGIN")
        try:
            for r in batch:
                primary_url = r.entities.urls[0] if r.entities.urls else None
                primary_email = r.entities.emails[0] if r.entities.emails else None
                primary_username = r.entities.usernames[0] if r.entities.usernames else None
                primary_hash = r.entities.hashes[0].value if r.entities.hashes else None
                primary_ip = (r.entities.ipv4s[0] if r.entities.ipv4s else (r.entities.ipv6s[0] if r.entities.ipv6s else None))
                primary_phone = r.entities.phones[0] if r.entities.phones else None
                primary_secret = r.entities.secrets[0].kind if r.entities.secrets else None
                primary_email_domain = r.entities.email_domains[0] if r.entities.email_domains else None

                normalized_url = primary_url.normalized if primary_url else None
                url_path = primary_url.path if primary_url else None
                host = primary_url.host if primary_url else None
                root_domain = primary_url.root_domain if primary_url else None
                subdomain = primary_url.subdomain if primary_url else None
                endpoint_type = primary_url.endpoint_type if primary_url else None
                service_name = primary_url.service_name if primary_url else None

                fts_values = (
                    r.searchable_text, source_id, file_id, file_path_str, file_name, extension,
                    r.line_number, r.byte_offset, r.byte_length, format_str,
                    service_name, root_domain, host, subdomain, normalized_url, url_path, endpoint_type,
                    primary_email, primary_email_domain, primary_username, primary_ip, primary_phone,
                    primary_hash, primary_secret, r.dedupe.record_hash, r.dedupe.account_hash, r.dedupe.url_hash,
                )
                fts_cur = await conn.execute(fts_sql, fts_values)
                fts_rowid = int(fts_cur.lastrowid)
                try:
                    record_cur = await conn.execute(
                        record_sql,
                        (
                            fts_rowid, source_id, file_id, file_path_str, file_name, extension,
                            r.line_number, r.byte_offset, r.byte_length, format_str,
                            service_name, root_domain, host, subdomain, normalized_url, url_path, endpoint_type,
                            primary_email, primary_email_domain, primary_username, primary_ip, primary_phone,
                            primary_hash, primary_secret, r.searchable_text, r.dedupe.record_hash,
                            r.dedupe.account_hash, r.dedupe.url_hash,
                        ),
                    )
                except Exception:
                    await conn.execute("DELETE FROM records_fts WHERE rowid = ?", (fts_rowid,))
                    raise
                record_id = int(record_cur.lastrowid)
                inserted += 1

                seen: set[tuple[str, str]] = set()
                for entity_type, value, entity_service, entity_domain in iter_entities(r):
                    normalized = _norm(entity_type, value)
                    key = (entity_type, normalized)
                    if not normalized or key in seen:
                        continue
                    seen.add(key)
                    await conn.execute(
                        """
                        INSERT OR IGNORE INTO record_entities(
                            record_id, entity_type, value, normalized_value, service_name, root_domain
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (record_id, entity_type, value, normalized, entity_service, entity_domain),
                    )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return inserted


async def delete_file_index(state: AppState, source_id: int, file_path: str) -> None:
    """Remove structured, FTS, entity and file metadata for one file."""
    async with state.db._lock:
        conn = state.db.conn
        await conn.execute("BEGIN IMMEDIATE")
        try:
            cur = await conn.execute(
                "SELECT fts_rowid FROM records WHERE source_id = ? AND file_path = ?",
                (source_id, file_path),
            )
            rowids = [row[0] for row in await cur.fetchall()]
            await conn.execute("DELETE FROM records WHERE source_id = ? AND file_path = ?", (source_id, file_path))
            if rowids:
                await conn.executemany("DELETE FROM records_fts WHERE rowid = ?", [(rid,) for rid in rowids])
            await conn.execute("DELETE FROM files WHERE source_id = ? AND path = ?", (source_id, file_path))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
