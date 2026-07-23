"""Reliable indexing orchestration for local source folders."""
from __future__ import annotations

import asyncio
import datetime as dt
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from breachelens.db import Database
from breachelens.errors import IndexingError, NotFoundError
from breachelens.identities import rebuild_identities
from breachelens.ingest.format_detection import detect_format
from breachelens.ingest.index_writer import delete_file_index, write_batch
from breachelens.ingest.parser import parse_line
from breachelens.ingest.scanner import ScannedFile, scan_folder_detailed
from breachelens.state import AppState


@dataclass
class JobSnapshot:
    job_id: int
    source_id: int
    status: str
    started_at: str
    current_file: Optional[str] = None
    files_total: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    records_indexed: int = 0
    errors: int = 0
    lines_per_sec: float = 0.0
    mb_per_sec: float = 0.0
    elapsed_secs: float = 0.0
    eta_secs: Optional[float] = None


_current_job: Optional[JobSnapshot] = None
_cancel_event = asyncio.Event()


def get_current_job() -> Optional[JobSnapshot]:
    return _current_job


async def start_indexing(state: AppState, source_id: int, force: bool = False) -> int:
    global _current_job, _cancel_event
    if _current_job is not None:
        raise IndexingError("an indexing job is already running")

    source = await state.db.fetchone(
        "SELECT id, path, allowed_extensions, storage_mode FROM sources WHERE id = ?",
        (source_id,),
    )
    if source is None:
        raise NotFoundError(f"source id {source_id} not found")

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    cur = await state.db.execute(
        "INSERT INTO index_jobs(source_id, status, started_at) VALUES (?, 'running', ?)",
        (source_id, started_at),
    )
    job_id = int(cur.lastrowid or 0)
    await state.db.execute("UPDATE sources SET status='indexing' WHERE id=?", (source_id,))

    _cancel_event = asyncio.Event()
    _current_job = JobSnapshot(job_id=job_id, source_id=source_id, status="running", started_at=started_at)
    task = asyncio.create_task(
        _run_job(state, job_id, source_id, str(source["path"]), str(source["allowed_extensions"]), force)
    )
    task.add_done_callback(_task_done_callback)
    return job_id


def _task_done_callback(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        import logging
        logging.getLogger("breachelens").exception("indexing task failed", exc_info=exc)


async def cancel_indexing(state: AppState) -> None:
    _cancel_event.set()
    if _current_job:
        await state.db.execute(
            "UPDATE index_jobs SET status='cancelled', finished_at=datetime('now') WHERE id=?",
            (_current_job.job_id,),
        )
        await state.db.execute("UPDATE sources SET status='pending' WHERE id=?", (_current_job.source_id,))


async def list_jobs(state: AppState, limit: int = 20) -> List[dict]:
    rows = await state.db.fetchall(
        """
        SELECT id, source_id, status, started_at, finished_at, files_total,
               files_processed, files_skipped, records_indexed, errors_count,
               throughput_lps, throughput_mbs, current_file, error_message
        FROM index_jobs ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    )
    return [dict(row) for row in rows]


async def list_job_errors(state: AppState, job_id: int) -> List[dict]:
    rows = await state.db.fetchall(
        "SELECT file_path, line_number, message, severity, timestamp FROM index_errors WHERE job_id=? ORDER BY id",
        (job_id,),
    )
    return [dict(row) for row in rows]


async def _run_job(state: AppState, job_id: int, source_id: int, source_path: str, allowed_exts_str: str, force: bool) -> None:
    global _current_job
    started = time.monotonic()
    records_added = 0
    files_processed = 0
    files_skipped = 0
    errors_total = 0
    processed_bytes = 0

    try:
        root = Path(source_path)
        allowed_exts = [item.strip().lstrip(".").lower() for item in allowed_exts_str.split(",") if item.strip()]
        scan = await asyncio.to_thread(scan_folder_detailed, root, allowed_exts)
        files = scan.files
        current_paths = {str(item.path) for item in files}

        await state.db.execute(
            "UPDATE index_jobs SET files_total=?, errors_count=? WHERE id=?",
            (len(files), len(scan.errors), job_id),
        )
        errors_total += len(scan.errors)
        for message in scan.errors:
            await state.db.execute(
                "INSERT INTO index_errors(job_id, file_path, message, severity) VALUES (?, ?, ?, 'warning')",
                (job_id, source_path, message),
            )

        if _current_job:
            _current_job.files_total = len(files)
            _current_job.errors = errors_total

        known = await state.db.fetchall("SELECT path FROM files WHERE source_id=?", (source_id,))
        for row in known:
            old_path = str(row["path"])
            if old_path not in current_paths:
                await delete_file_index(state, source_id, old_path)

        if not files:
            raise IndexingError(
                f"no matching files found. Allowed extensions: {', '.join('.'+e for e in allowed_exts) or 'all'}"
            )

        for scanned in files:
            if _cancel_event.is_set():
                break
            if _current_job:
                _current_job.current_file = str(scanned.path)

            unchanged = (not force) and state.config.indexing.skip_unchanged and await _is_file_unchanged(state.db, scanned, source_id)
            if unchanged:
                files_skipped += 1
                _update_snapshot(started, files_processed, files_skipped, records_added, errors_total, processed_bytes, len(files))
                continue

            try:
                await delete_file_index(state, source_id, str(scanned.path))
                added = await _index_file(state, source_id, scanned, state.config.indexing.batch_size)
                records_added += added
                files_processed += 1
                processed_bytes += scanned.size_bytes
            except Exception as exc:
                errors_total += 1
                await delete_file_index(state, source_id, str(scanned.path))
                await state.db.execute(
                    "INSERT INTO index_errors(job_id, file_path, message, severity) VALUES (?, ?, ?, 'error')",
                    (job_id, str(scanned.path), str(exc)),
                )

            _update_snapshot(started, files_processed, files_skipped, records_added, errors_total, processed_bytes, len(files))
            snap = _current_job
            await state.db.execute(
                """
                UPDATE index_jobs SET files_processed=?, files_skipped=?, records_indexed=?,
                    errors_count=?, throughput_lps=?, throughput_mbs=?, current_file=?
                WHERE id=?
                """,
                (files_processed, files_skipped, records_added, errors_total,
                 snap.lines_per_sec if snap else 0, snap.mb_per_sec if snap else 0,
                 str(scanned.path), job_id),
            )

        if _cancel_event.is_set():
            final_status = "cancelled"
            source_status = "pending"
        else:
            await rebuild_identities(state.db)
            final_status = "completed_with_errors" if errors_total else "completed"
            source_status = "indexed"

        totals = await state.db.fetchone(
            """
            SELECT COUNT(DISTINCT f.id) AS files_count,
                   COALESCE(SUM(f.size_bytes),0) AS size_bytes,
                   (SELECT COUNT(*) FROM records r WHERE r.source_id=?) AS records_count
            FROM files f WHERE f.source_id=?
            """,
            (source_id, source_id),
        )
        await state.db.execute(
            """
            UPDATE sources SET status=?, files_count=?, records_count=?, size_bytes=?, last_indexed_at=datetime('now')
            WHERE id=?
            """,
            (source_status, int(totals["files_count"] or 0), int(totals["records_count"] or 0),
             int(totals["size_bytes"] or 0), source_id),
        )
        await state.db.execute(
            """
            UPDATE index_jobs SET status=?, finished_at=datetime('now'), files_processed=?,
                files_skipped=?, records_indexed=?, errors_count=?, current_file=NULL
            WHERE id=?
            """,
            (final_status, files_processed, files_skipped, records_added, errors_total, job_id),
        )
    except Exception as exc:
        await state.db.execute(
            "UPDATE index_jobs SET status='failed', finished_at=datetime('now'), error_message=? WHERE id=?",
            (str(exc), job_id),
        )
        await state.db.execute("UPDATE sources SET status='error' WHERE id=?", (source_id,))
        if _current_job:
            _current_job.status = "failed"
            _current_job.errors += 1
    finally:
        _current_job = None


def _update_snapshot(started: float, processed: int, skipped: int, records: int, errors: int,
                     processed_bytes: int, total: int) -> None:
    if not _current_job:
        return
    elapsed = max(0.001, time.monotonic() - started)
    completed = processed + skipped
    _current_job.files_processed = processed
    _current_job.files_skipped = skipped
    _current_job.records_indexed = records
    _current_job.errors = errors
    _current_job.lines_per_sec = records / elapsed
    _current_job.mb_per_sec = (processed_bytes / (1024 * 1024)) / elapsed
    _current_job.elapsed_secs = elapsed
    _current_job.eta_secs = (elapsed / completed) * (total - completed) if completed else None


async def _is_file_unchanged(db: Database, item: ScannedFile, source_id: int) -> bool:
    row = await db.fetchone(
        "SELECT mtime, size_bytes, status FROM files WHERE source_id=? AND path=?",
        (source_id, str(item.path)),
    )
    return bool(row and row["status"] == "indexed" and row["mtime"] == item.mtime and row["size_bytes"] == item.size_bytes)


async def _index_file(state: AppState, source_id: int, item: ScannedFile, batch_size: int) -> int:
    path = item.path
    with open(path, "rb") as handle:
        sample = handle.read(8192)
    fmt = detect_format(path, sample)

    cur = await state.db.execute(
        """
        INSERT INTO files(source_id, path, file_name, extension, size_bytes, mtime, detected_format, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'indexing')
        """,
        (source_id, str(path), item.file_name, item.extension, item.size_bytes, item.mtime, fmt.value),
    )
    file_id = int(cur.lastrowid or 0)

    records_indexed = 0
    line_count = 0
    byte_offset = 0
    batch = []
    max_len = state.config.indexing.max_line_length

    with open(path, "rb") as handle:
        for raw in handle:
            line_count += 1
            line_start = byte_offset
            byte_offset += len(raw)
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not text:
                continue
            if len(text) > max_len:
                text = text[:max_len]
            batch.append(parse_line(text, line_count, line_start, fmt, byte_length=min(len(raw), max_len * 4)))
            if len(batch) >= batch_size:
                records_indexed += await write_batch(state, batch, source_id, file_id, path, fmt.value)
                batch.clear()
    if batch:
        records_indexed += await write_batch(state, batch, source_id, file_id, path, fmt.value)

    await state.db.execute(
        """
        UPDATE files SET line_count=?, records_indexed=?, last_indexed_at=?, status='indexed'
        WHERE id=?
        """,
        (line_count, records_indexed, dt.datetime.now(dt.timezone.utc).isoformat(), file_id),
    )
    return records_indexed
