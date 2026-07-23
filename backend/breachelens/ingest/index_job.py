"""Indexing job orchestration: scan, stream, parse, and batch-write records."""
from __future__ import annotations

import asyncio
import datetime
import itertools
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from breachelens.db import Database
from breachelens.errors import IndexingError
from breachelens.ingest.format_detection import detect_format
from breachelens.ingest.index_writer import write_batch
from breachelens.ingest.parser import parse_line
from breachelens.ingest.scanner import ScannedFile, scan_folder_detailed
from breachelens.state import AppState

log = logging.getLogger("breachelens")


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


async def start_indexing(state: AppState, source_id: int) -> int:
    """Start an indexing job for a source and return its database job ID."""
    global _current_job, _cancel_event
    if _current_job is not None:
        raise IndexingError("an indexing job is already running")

    source_row = await state.db.fetchone(
        "SELECT id, path, allowed_extensions FROM sources WHERE id = ?",
        (source_id,),
    )
    if source_row is None:
        from breachelens.errors import NotFoundError

        raise NotFoundError(f"source id {source_id} not found")

    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = await state.db.execute(
        "INSERT INTO index_jobs (source_id, status, started_at) VALUES (?, 'running', ?)",
        (source_id, started_at),
    )
    job_id = int(cur.lastrowid or 0)
    await state.db.execute("UPDATE sources SET status = 'indexing' WHERE id = ?", (source_id,))

    _cancel_event = asyncio.Event()
    _current_job = JobSnapshot(
        job_id=job_id,
        source_id=source_id,
        status="running",
        started_at=started_at,
    )

    task = asyncio.create_task(
        _run_job(state, job_id, source_id, source_row["path"], source_row["allowed_extensions"])
    )
    task.add_done_callback(_task_done_callback)
    return job_id


def _task_done_callback(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("indexing task failed: %r", exc, exc_info=exc)


async def cancel_indexing(state: AppState) -> None:
    _cancel_event.set()
    if _current_job is not None:
        _current_job.status = "cancelling"
        await state.db.execute(
            "UPDATE index_jobs SET status = 'cancelling' WHERE id = ?",
            (_current_job.job_id,),
        )


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


async def list_job_errors(state: AppState, job_id: int, limit: int = 100) -> List[dict]:
    rows = await state.db.fetchall(
        """
        SELECT file_path, line_number, message, severity, timestamp
        FROM index_errors
        WHERE job_id = ?
        ORDER BY id DESC LIMIT ?
        """,
        (job_id, limit),
    )
    return [dict(row) for row in rows]


async def _run_job(
    state: AppState,
    job_id: int,
    source_id: int,
    source_path: str,
    allowed_exts_str: str,
) -> None:
    global _current_job
    started = time.monotonic()
    try:
        root = Path(source_path)
        allowed_exts = [
            value.strip().lower().lstrip(".")
            for value in allowed_exts_str.split(",")
            if value.strip()
        ]
        max_size = state.config.indexing.max_file_size_mb * 1024 * 1024
        scan = await asyncio.to_thread(
            scan_folder_detailed,
            root,
            allowed_exts,
            max_file_size_bytes=max_size,
        )
        files = scan.files

        await state.db.execute(
            "UPDATE index_jobs SET files_total = ? WHERE id = ?",
            (len(files), job_id),
        )
        if _current_job:
            _current_job.files_total = len(files)

        for warning in scan.errors[:100]:
            await state.db.execute(
                "INSERT INTO index_errors (job_id, file_path, message, severity) VALUES (?, ?, ?, 'warning')",
                (job_id, str(root), warning),
            )

        if not files:
            extensions = ", ".join(f".{ext}" for ext in allowed_exts)
            extra = ""
            if scan.skipped_large_files:
                extra = f"; {scan.skipped_large_files} files exceeded the size limit"
            raise IndexingError(
                f"No readable supported files found in {root}. Allowed extensions: {extensions}{extra}"
            )

        # Only remove stale files when the scan itself had no directory-access errors.
        if not scan.errors:
            await _remove_missing_files(state, source_id, {str(item.path) for item in files})

        records_new = 0
        errors_total = len(scan.errors)
        files_processed = 0
        files_skipped = 0
        bytes_done = 0
        batch_size = state.config.indexing.batch_size

        for scanned_file in files:
            if _cancel_event.is_set():
                await _mark_cancelled(state, job_id, source_id)
                return

            if _current_job:
                _current_job.current_file = str(scanned_file.path)

            if state.config.indexing.skip_unchanged and await _is_file_unchanged(
                state.db, source_id, scanned_file
            ):
                files_skipped += 1
                bytes_done += scanned_file.size_bytes
                await _update_progress(
                    state,
                    job_id,
                    started,
                    files_processed,
                    files_skipped,
                    records_new,
                    errors_total,
                    bytes_done,
                    len(files),
                    str(scanned_file.path),
                )
                continue

            try:
                # A changed file replaces its prior rows instead of duplicating them.
                await _purge_file_records(state, source_id, str(scanned_file.path), delete_file_row=False)
                indexed = await _index_file(
                    state,
                    source_id,
                    scanned_file,
                    batch_size,
                )
                records_new += indexed
                files_processed += 1
            except Exception as exc:
                errors_total += 1
                await _mark_file_error(state, source_id, scanned_file)
                await state.db.execute(
                    "INSERT INTO index_errors (job_id, file_path, message, severity) VALUES (?, ?, ?, 'error')",
                    (job_id, str(scanned_file.path), str(exc)),
                )
                log.exception("failed to index %s", scanned_file.path)

            bytes_done += scanned_file.size_bytes
            await _update_progress(
                state,
                job_id,
                started,
                files_processed,
                files_skipped,
                records_new,
                errors_total,
                bytes_done,
                len(files),
                str(scanned_file.path),
            )

        elapsed = time.monotonic() - started
        lps = records_new / elapsed if elapsed > 0 else 0.0
        totals = await state.db.fetchone(
            """
            SELECT COUNT(*) AS files_count,
                   COALESCE(SUM(records_indexed), 0) AS records_count,
                   COALESCE(SUM(size_bytes), 0) AS size_bytes
            FROM files WHERE source_id = ?
            """,
            (source_id,),
        )
        source_status = "indexed_with_errors" if errors_total else "indexed"
        summary = f"Completed with {errors_total} warning/error(s)" if errors_total else None

        await state.db.execute(
            """
            UPDATE index_jobs
            SET status = 'completed', finished_at = datetime('now'),
                files_processed = ?, files_skipped = ?, records_indexed = ?,
                errors_count = ?, throughput_lps = ?, throughput_mbs = ?,
                current_file = NULL, error_message = ?
            WHERE id = ?
            """,
            (
                files_processed,
                files_skipped,
                records_new,
                errors_total,
                lps,
                (bytes_done / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0,
                summary,
                job_id,
            ),
        )
        await state.db.execute(
            """
            UPDATE sources
            SET status = ?, records_count = ?, files_count = ?, size_bytes = ?,
                last_indexed_at = datetime('now')
            WHERE id = ?
            """,
            (
                source_status,
                int(totals["records_count"] if totals else 0),
                int(totals["files_count"] if totals else 0),
                int(totals["size_bytes"] if totals else 0),
                source_id,
            ),
        )

    except Exception as exc:
        message = str(exc)
        await state.db.execute(
            "UPDATE index_jobs SET status = 'failed', finished_at = datetime('now'), error_message = ? WHERE id = ?",
            (message, job_id),
        )
        await state.db.execute(
            "UPDATE sources SET status = 'error' WHERE id = ?",
            (source_id,),
        )
        log.error("indexing job %s failed: %s", job_id, message)
    finally:
        _current_job = None


async def _mark_cancelled(state: AppState, job_id: int, source_id: int) -> None:
    await state.db.execute(
        "UPDATE index_jobs SET status = 'cancelled', finished_at = datetime('now'), current_file = NULL WHERE id = ?",
        (job_id,),
    )
    await state.db.execute(
        "UPDATE sources SET status = 'pending' WHERE id = ?",
        (source_id,),
    )


async def _update_progress(
    state: AppState,
    job_id: int,
    started: float,
    files_processed: int,
    files_skipped: int,
    records_indexed: int,
    errors: int,
    bytes_done: int,
    files_total: int,
    current_file: str,
) -> None:
    elapsed = time.monotonic() - started
    completed = files_processed + files_skipped
    lps = records_indexed / elapsed if elapsed > 0 else 0.0
    mbs = (bytes_done / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
    eta = (elapsed / completed) * (files_total - completed) if completed > 0 else None

    if _current_job:
        _current_job.files_processed = files_processed
        _current_job.files_skipped = files_skipped
        _current_job.records_indexed = records_indexed
        _current_job.errors = errors
        _current_job.lines_per_sec = lps
        _current_job.mb_per_sec = mbs
        _current_job.elapsed_secs = elapsed
        _current_job.eta_secs = eta

    await state.db.execute(
        """
        UPDATE index_jobs
        SET files_processed = ?, files_skipped = ?, records_indexed = ?,
            errors_count = ?, throughput_lps = ?, throughput_mbs = ?, current_file = ?
        WHERE id = ?
        """,
        (
            files_processed,
            files_skipped,
            records_indexed,
            errors,
            lps,
            mbs,
            current_file,
            job_id,
        ),
    )


async def _is_file_unchanged(db: Database, source_id: int, scanned_file: ScannedFile) -> bool:
    row = await db.fetchone(
        "SELECT mtime, size_bytes FROM files WHERE source_id = ? AND path = ?",
        (source_id, str(scanned_file.path)),
    )
    if row is None:
        return False
    return row["mtime"] == scanned_file.mtime and row["size_bytes"] == scanned_file.size_bytes


async def _remove_missing_files(state: AppState, source_id: int, scanned_paths: set[str]) -> None:
    existing = await state.db.fetchall("SELECT path FROM files WHERE source_id = ?", (source_id,))
    for row in existing:
        path = str(row["path"])
        if path not in scanned_paths:
            await _purge_file_records(state, source_id, path, delete_file_row=True)


async def _purge_file_records(
    state: AppState,
    source_id: int,
    file_path: str,
    *,
    delete_file_row: bool,
) -> None:
    rows = await state.db.fetchall(
        "SELECT fts_rowid FROM records WHERE source_id = ? AND file_path = ?",
        (source_id, file_path),
    )
    async with state.db._lock:
        for row in rows:
            await state.db.conn.execute("DELETE FROM records_fts WHERE rowid = ?", (row["fts_rowid"],))
        await state.db.conn.execute(
            "DELETE FROM records WHERE source_id = ? AND file_path = ?",
            (source_id, file_path),
        )
        if delete_file_row:
            await state.db.conn.execute(
                "DELETE FROM files WHERE source_id = ? AND path = ?",
                (source_id, file_path),
            )
        await state.db.conn.commit()


async def _mark_file_error(state: AppState, source_id: int, scanned_file: ScannedFile) -> None:
    await state.db.execute(
        """
        INSERT INTO files (
            source_id, path, file_name, extension, size_bytes, line_count,
            records_indexed, mtime, detected_format, last_indexed_at, status
        )
        VALUES (?, ?, ?, ?, ?, 0, 0, ?, NULL, datetime('now'), 'error')
        ON CONFLICT(source_id, path) DO UPDATE SET
            size_bytes = excluded.size_bytes,
            records_indexed = 0,
            mtime = excluded.mtime,
            last_indexed_at = excluded.last_indexed_at,
            status = 'error'
        """,
        (
            source_id,
            str(scanned_file.path),
            scanned_file.file_name,
            scanned_file.extension,
            scanned_file.size_bytes,
            scanned_file.mtime,
        ),
    )


async def _index_file(
    state: AppState,
    source_id: int,
    scanned_file: ScannedFile,
    batch_size: int,
) -> int:
    """Stream one file in bounded chunks and batch-insert parsed records."""
    path = scanned_file.path

    def read_sample() -> bytes:
        with open(path, "rb") as handle:
            return handle.read(8192)

    try:
        sample = await asyncio.to_thread(read_sample)
    except OSError:
        sample = b""

    detected_format = detect_format(path, sample)
    format_name = detected_format.value
    records_indexed = 0
    line_number = 0
    byte_offset = 0
    total_lines = 0
    parse_batch: list = []
    read_chunk_size = max(256, min(batch_size, 8192))

    with open(path, "rb") as handle:
        while True:
            raw_lines = await asyncio.to_thread(
                lambda: list(itertools.islice(handle, read_chunk_size))
            )
            if not raw_lines:
                break

            for raw_line in raw_lines:
                line_number += 1
                total_lines += 1
                line_start = byte_offset
                byte_offset += len(raw_line)
                text = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not text:
                    continue
                if len(text) > state.config.indexing.max_line_length:
                    text = text[: state.config.indexing.max_line_length]

                parse_batch.append(parse_line(text, line_number, line_start, detected_format))
                if len(parse_batch) >= batch_size:
                    records_indexed += await write_batch(
                        state,
                        parse_batch,
                        source_id,
                        path,
                        format_name,
                    )
                    parse_batch.clear()

    if parse_batch:
        records_indexed += await write_batch(
            state,
            parse_batch,
            source_id,
            path,
            format_name,
        )

    indexed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    await state.db.execute(
        """
        INSERT INTO files (
            source_id, path, file_name, extension, size_bytes, line_count,
            records_indexed, mtime, detected_format, last_indexed_at, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed')
        ON CONFLICT(source_id, path) DO UPDATE SET
            size_bytes = excluded.size_bytes,
            line_count = excluded.line_count,
            records_indexed = excluded.records_indexed,
            mtime = excluded.mtime,
            detected_format = excluded.detected_format,
            last_indexed_at = excluded.last_indexed_at,
            status = 'indexed'
        """,
        (
            source_id,
            str(path),
            scanned_file.file_name,
            scanned_file.extension,
            scanned_file.size_bytes,
            total_lines,
            records_indexed,
            scanned_file.mtime,
            format_name,
            indexed_at,
        ),
    )
    return records_indexed
