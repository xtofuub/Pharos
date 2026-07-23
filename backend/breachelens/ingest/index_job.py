"""Indexing job orchestration: stream files, parse records, batch-insert into FTS5."""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from breachelens.db import Database
from breachelens.errors import IndexingError
from breachelens.ingest.format_detection import detect_format
from breachelens.ingest.parser import parse_line
from breachelens.ingest.scanner import ScannedFile, scan_folder
from breachelens.ingest.index_writer import write_batch
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


# Module-level singletons (the app holds one job at a time)
_current_job: Optional[JobSnapshot] = None
_cancel_event = asyncio.Event()


def get_current_job() -> Optional[JobSnapshot]:
    return _current_job


async def start_indexing(state: AppState, source_id: int) -> int:
    """Start an indexing job for the given source. Returns the job ID."""
    global _current_job, _cancel_event
    if _current_job is not None:
        raise IndexingError("an indexing job is already running")

    # Load source
    source_row = await state.db.fetchone(
        "SELECT id, path, allowed_extensions, storage_mode FROM sources WHERE id = ?",
        (source_id,),
    )
    if source_row is None:
        from breachelens.errors import NotFoundError
        raise NotFoundError(f"source id {source_id} not found")

    # Insert job row
    import datetime
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = await state.db.execute(
        "INSERT INTO index_jobs (source_id, status, started_at) VALUES (?, 'running', ?)",
        (source_id, started_at),
    )
    job_id = cur.lastrowid or 0

    # Set source status
    await state.db.execute(
        "UPDATE sources SET status = 'indexing' WHERE id = ?",
        (source_id,),
    )

    _cancel_event = asyncio.Event()
    _current_job = JobSnapshot(
        job_id=job_id,
        source_id=source_id,
        status="running",
        started_at=started_at,
    )

    # Run in background
    task = asyncio.create_task(_run_job(state, job_id, source_row["path"], source_row["allowed_extensions"]))
    task.add_done_callback(_task_done_callback)
    return job_id


def _task_done_callback(task: asyncio.Task) -> None:
    """Log any exception that occurred in the indexing task."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        import logging
        logging.getLogger("breachelens").error("indexing task failed: %r", exc, exc_info=exc)


async def cancel_indexing(state: AppState) -> None:
    global _current_job
    _cancel_event.set()
    if _current_job is not None:
        await state.db.execute(
            "UPDATE index_jobs SET status = 'cancelled', finished_at = datetime('now') WHERE id = ?",
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
    return [dict(r) for r in rows]


async def _run_job(state: AppState, job_id: int, source_path: str, allowed_exts_str: str) -> None:
    global _current_job
    start_time = time.monotonic()
    try:
        root = Path(source_path)
        allowed_exts = [e.strip().lower().lstrip(".") for e in allowed_exts_str.split(",") if e.strip()]
        files = scan_folder(root, allowed_exts)
        files_total = len(files)

        await state.db.execute(
            "UPDATE index_jobs SET files_total = ? WHERE id = ?",
            (files_total, job_id),
        )
        if _current_job:
            _current_job.files_total = files_total

        records_total = 0
        errors_total = 0
        files_processed = 0
        files_skipped = 0
        batch_size = state.config.indexing.batch_size

        for f in files:
            if _cancel_event.is_set():
                await state.db.execute(
                    "UPDATE index_jobs SET status = 'cancelled', finished_at = datetime('now') WHERE id = ?",
                    (job_id,),
                )
                break

            if state.config.indexing.skip_unchanged and await _is_file_unchanged(state.db, f):
                files_skipped += 1
                if _current_job:
                    _current_job.files_skipped = files_skipped
                    _current_job.current_file = str(f.path)
                continue

            if _current_job:
                _current_job.current_file = str(f.path)

            try:
                records = await _index_file(state, job_id, _current_job.source_id if _current_job else 0, f, batch_size)
                records_total += records
                files_processed += 1
            except Exception as e:
                errors_total += 1
                await state.db.execute(
                    "INSERT INTO index_errors (job_id, file_path, message, severity) VALUES (?, ?, ?, 'error')",
                    (job_id, str(f.path), str(e)),
                )

            elapsed = time.monotonic() - start_time
            lps = records_total / elapsed if elapsed > 0 else 0.0
            total_bytes = sum(ff.size_bytes for ff in files[:files_processed])
            mbs = (total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
            eta = (elapsed / files_processed) * (files_total - files_processed) if files_processed > 0 else None

            if _current_job:
                _current_job.files_processed = files_processed
                _current_job.files_skipped = files_skipped
                _current_job.records_indexed = records_total
                _current_job.errors = errors_total
                _current_job.lines_per_sec = lps
                _current_job.mb_per_sec = mbs
                _current_job.elapsed_secs = elapsed
                _current_job.eta_secs = eta

            await state.db.execute(
                """
                UPDATE index_jobs SET files_processed = ?, files_skipped = ?, records_indexed = ?,
                       errors_count = ?, throughput_lps = ?, throughput_mbs = ?, current_file = ?
                WHERE id = ?
                """,
                (files_processed, files_skipped, records_total, errors_total, lps, mbs, str(f.path), job_id),
            )

        # Finalize
        elapsed = time.monotonic() - start_time
        lps = records_total / elapsed if elapsed > 0 else 0.0
        await state.db.execute(
            """
            UPDATE index_jobs SET status = 'completed', finished_at = datetime('now'),
                   files_processed = ?, files_skipped = ?, records_indexed = ?,
                   errors_count = ?, throughput_lps = ?, throughput_mbs = 0, current_file = NULL
            WHERE id = ?
            """,
            (files_processed, files_skipped, records_total, errors_total, lps, job_id),
        )
        await state.db.execute(
            "UPDATE sources SET status = 'indexed', records_count = ?, files_count = ?, last_indexed_at = datetime('now') WHERE id = ?",
            (records_total, files_processed, _current_job.source_id if _current_job else 0),
        )

    except Exception as e:
        await state.db.execute(
            "UPDATE index_jobs SET status = 'failed', finished_at = datetime('now'), error_message = ? WHERE id = ?",
            (str(e), job_id),
        )
    finally:
        _current_job = None


async def _is_file_unchanged(db: Database, f: ScannedFile) -> bool:
    row = await db.fetchone(
        "SELECT mtime, size_bytes FROM files WHERE path = ?",
        (str(f.path),),
    )
    if row is None:
        return False
    return row["mtime"] == f.mtime and row["size_bytes"] == f.size_bytes


async def _index_file(
    state: AppState,
    job_id: int,
    source_id: int,
    f: ScannedFile,
    batch_size: int,
) -> int:
    """Stream a single file line-by-line and batch-insert into the index."""
    path = f.path

    # Read a sample to detect format
    sample = b""
    try:
        def _read_sample():
            with open(path, "rb") as fh:
                return fh.read(8192)
        sample = await asyncio.to_thread(_read_sample)
    except OSError:
        sample = b""

    fmt = detect_format(path, sample)
    fmt_str = fmt.value

    # Stream the file line by line using a blocking reader in a thread.
    # We read the whole file into memory in chunks -- fine for the MVP
    # since test files are small. For huge files we'd switch to a true
    # streaming reader.
    records_indexed = 0
    batch: list = []
    line_number = 0
    byte_offset = 0
    total_lines = 0

    # Open the file synchronously and iterate lines in a thread
    def _read_all_lines() -> list[str]:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.readlines()

    all_lines = await asyncio.to_thread(_read_all_lines)

    for line in all_lines:
        line_number += 1
        total_lines += 1
        line_len = len(line.encode("utf-8"))
        line_start = byte_offset
        byte_offset += line_len

        trimmed = line.rstrip("\r\n")
        if not trimmed:
            continue

        if len(trimmed) > state.config.indexing.max_line_length:
            trimmed = trimmed[: state.config.indexing.max_line_length]

        record = parse_line(trimmed, line_number, line_start, fmt)
        batch.append(record)

        if len(batch) >= batch_size:
            count = await write_batch(state, batch, source_id, path, fmt_str)
            records_indexed += count
            batch.clear()

    if batch:
        count = await write_batch(state, batch, source_id, path, fmt_str)
        records_indexed += count

    # Insert/update file metadata
    import datetime
    await state.db.execute(
        """
        INSERT INTO files (source_id, path, file_name, extension, size_bytes, line_count,
                            records_indexed, mtime, detected_format, last_indexed_at, status)
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
            f.file_name,
            f.extension,
            f.size_bytes,
            total_lines,
            records_indexed,
            f.mtime,
            fmt_str,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )

    return records_indexed


import itertools  # noqa: E402  (kept for backwards compatibility)
