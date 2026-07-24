"""Reliable indexing orchestration for local source folders."""
from __future__ import annotations

import asyncio
import datetime as dt
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

from breachelens.db import Database
from breachelens.errors import IndexingError, NotFoundError
from breachelens.identities import rebuild_identities
from breachelens.ingest.format_detection import detect_format
from breachelens.ingest.index_writer import delete_file_index, write_batch
from breachelens.ingest.parser import parse_line
from breachelens.ingest.scanner import ScannedFile, scan_folder_detailed
from breachelens.state import AppState


ProgressCallback = Callable[[int, int, int], Awaitable[None]]


@dataclass
class FileIndexResult:
    records_indexed: int
    line_count: int
    warnings: int = 0


@dataclass
class JobSnapshot:
    job_id: int
    source_id: int
    status: str
    started_at: str
    phase: str = "scanning"
    current_file: Optional[str] = None
    files_total: int = 0
    files_processed: int = 0
    files_failed: int = 0
    files_skipped: int = 0
    records_indexed: int = 0
    warnings: int = 0
    errors: int = 0
    bytes_total: int = 0
    bytes_processed: int = 0
    current_file_bytes: int = 0
    current_file_size: int = 0
    current_line: int = 0
    progress_percent: float = 0.0
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
        _current_job.status = "cancelled"
        _current_job.phase = "cancelled"
        await state.db.execute(
            "UPDATE index_jobs SET status='cancelled', finished_at=datetime('now') WHERE id=?",
            (_current_job.job_id,),
        )
        await state.db.execute("UPDATE sources SET status='pending' WHERE id=?", (_current_job.source_id,))


async def list_jobs(state: AppState, limit: int = 20) -> List[dict]:
    rows = await state.db.fetchall(
        """
        SELECT id, source_id, status, started_at, finished_at, files_total,
               files_processed, files_failed, files_skipped, records_indexed,
               warnings_count, errors_count, throughput_lps, throughput_mbs,
               current_file, error_message
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


async def _run_job(
    state: AppState,
    job_id: int,
    source_id: int,
    source_path: str,
    allowed_exts_str: str,
    force: bool,
) -> None:
    global _current_job
    started = time.monotonic()
    records_added = 0
    files_processed = 0
    files_failed = 0
    files_skipped = 0
    warnings_total = 0
    errors_total = 0
    processed_bytes = 0
    total_bytes = 0

    try:
        root = Path(source_path)
        allowed_exts = [item.strip().lstrip(".").lower() for item in allowed_exts_str.split(",") if item.strip()]
        scan = await asyncio.to_thread(scan_folder_detailed, root, allowed_exts)
        files = scan.files
        current_paths = {str(item.path) for item in files}
        total_bytes = sum(item.size_bytes for item in files)
        warnings_total = len(scan.errors)

        await state.db.execute(
            "UPDATE index_jobs SET files_total=?, warnings_count=?, errors_count=0 WHERE id=?",
            (len(files), warnings_total, job_id),
        )
        for message in scan.errors:
            await state.db.execute(
                "INSERT INTO index_errors(job_id, file_path, message, severity) VALUES (?, ?, ?, 'warning')",
                (job_id, source_path, message),
            )

        if _current_job:
            _current_job.phase = "preparing"
            _current_job.files_total = len(files)
            _current_job.warnings = warnings_total
            _current_job.bytes_total = total_bytes

        known = await state.db.fetchall("SELECT path FROM files WHERE source_id=?", (source_id,))
        for row in known:
            old_path = str(row["path"])
            if old_path not in current_paths:
                await delete_file_index(state, source_id, old_path)

        if not files:
            raise IndexingError(
                f"no matching files found. Allowed extensions: {', '.join('.' + e for e in allowed_exts) or 'all'}"
            )

        for scanned in files:
            if _cancel_event.is_set():
                break

            if _current_job:
                _current_job.phase = "indexing"
                _current_job.current_file = str(scanned.path)
                _current_job.current_file_bytes = 0
                _current_job.current_file_size = scanned.size_bytes
                _current_job.current_line = 0

            unchanged = (
                (not force)
                and state.config.indexing.skip_unchanged
                and await _is_file_unchanged(state.db, scanned, source_id)
            )
            if unchanged:
                files_skipped += 1
                processed_bytes += scanned.size_bytes
                _update_snapshot(
                    started, files_processed, files_failed, files_skipped, records_added,
                    warnings_total, errors_total, processed_bytes, total_bytes, len(files),
                    current_file_bytes=scanned.size_bytes, current_file_size=scanned.size_bytes,
                )
                await _persist_progress(
                    state, job_id, files_processed, files_failed, files_skipped, records_added,
                    warnings_total, errors_total, scanned.path,
                )
                continue

            base_bytes = processed_bytes

            async def report_progress(file_bytes: int, file_records: int, line_count: int) -> None:
                _update_snapshot(
                    started, files_processed, files_failed, files_skipped,
                    records_added + file_records, warnings_total, errors_total,
                    base_bytes + min(file_bytes, scanned.size_bytes), total_bytes, len(files),
                    current_file_bytes=min(file_bytes, scanned.size_bytes),
                    current_file_size=scanned.size_bytes,
                    current_line=line_count,
                )
                await asyncio.sleep(0)

            try:
                await delete_file_index(state, source_id, str(scanned.path))
                result = await _index_file(
                    state, job_id, source_id, scanned, state.config.indexing.batch_size, report_progress
                )
                records_added += result.records_indexed
                warnings_total += result.warnings
            except Exception as exc:
                errors_total += 1
                files_failed += 1
                await delete_file_index(state, source_id, str(scanned.path))
                await state.db.execute(
                    "INSERT INTO index_errors(job_id, file_path, message, severity) VALUES (?, ?, ?, 'error')",
                    (job_id, str(scanned.path), f"{type(exc).__name__}: {exc}"),
                )
            finally:
                # A failed file is still a completed attempt. Advancing this counter prevents 0% jobs.
                files_processed += 1
                processed_bytes += scanned.size_bytes

            _update_snapshot(
                started, files_processed, files_failed, files_skipped, records_added,
                warnings_total, errors_total, processed_bytes, total_bytes, len(files),
                current_file_bytes=scanned.size_bytes, current_file_size=scanned.size_bytes,
            )
            await _persist_progress(
                state, job_id, files_processed, files_failed, files_skipped, records_added,
                warnings_total, errors_total, scanned.path,
            )

        if _cancel_event.is_set():
            final_status = "cancelled"
            source_status = "pending"
        else:
            if _current_job:
                _current_job.phase = "building_profiles"
                _current_job.current_file = None
                _current_job.current_file_bytes = 0
                _current_job.current_file_size = 0
            await rebuild_identities(state.db)
            final_status = "completed_with_errors" if errors_total else "completed"
            successful_files = files_processed - files_failed
            source_status = "error" if files_processed and successful_files == 0 else "indexed"

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
            (
                source_status,
                int(totals["files_count"] or 0),
                int(totals["records_count"] or 0),
                int(totals["size_bytes"] or 0),
                source_id,
            ),
        )
        await state.db.execute(
            """
            UPDATE index_jobs SET status=?, finished_at=datetime('now'), files_processed=?,
                files_failed=?, files_skipped=?, records_indexed=?, warnings_count=?, errors_count=?,
                current_file=NULL
            WHERE id=?
            """,
            (
                final_status, files_processed, files_failed, files_skipped, records_added,
                warnings_total, errors_total, job_id,
            ),
        )
        if _current_job:
            _current_job.status = final_status
            _current_job.phase = "finished"
            _current_job.progress_percent = 100.0
    except Exception as exc:
        await state.db.execute(
            """
            UPDATE index_jobs SET status='failed', finished_at=datetime('now'), error_message=?,
                files_processed=?, files_failed=?, files_skipped=?, records_indexed=?,
                warnings_count=?, errors_count=? WHERE id=?
            """,
            (
                f"{type(exc).__name__}: {exc}", files_processed, files_failed, files_skipped,
                records_added, warnings_total, errors_total + 1, job_id,
            ),
        )
        await state.db.execute("UPDATE sources SET status='error' WHERE id=?", (source_id,))
        if _current_job:
            _current_job.status = "failed"
            _current_job.phase = "failed"
            _current_job.errors = errors_total + 1
    finally:
        _current_job = None


async def _persist_progress(
    state: AppState,
    job_id: int,
    files_processed: int,
    files_failed: int,
    files_skipped: int,
    records_added: int,
    warnings_total: int,
    errors_total: int,
    current_file: Path,
) -> None:
    snap = _current_job
    await state.db.execute(
        """
        UPDATE index_jobs SET files_processed=?, files_failed=?, files_skipped=?, records_indexed=?,
            warnings_count=?, errors_count=?, throughput_lps=?, throughput_mbs=?, current_file=?
        WHERE id=?
        """,
        (
            files_processed,
            files_failed,
            files_skipped,
            records_added,
            warnings_total,
            errors_total,
            snap.lines_per_sec if snap else 0,
            snap.mb_per_sec if snap else 0,
            str(current_file),
            job_id,
        ),
    )


def _update_snapshot(
    started: float,
    processed: int,
    failed: int,
    skipped: int,
    records: int,
    warnings: int,
    errors: int,
    processed_bytes: int,
    total_bytes: int,
    total_files: int,
    *,
    current_file_bytes: int = 0,
    current_file_size: int = 0,
    current_line: int = 0,
) -> None:
    if not _current_job:
        return
    elapsed = max(0.001, time.monotonic() - started)
    completed_files = processed + skipped
    if total_bytes > 0:
        fraction = min(1.0, processed_bytes / total_bytes)
    else:
        fraction = min(1.0, completed_files / total_files) if total_files else 0.0

    _current_job.files_processed = processed
    _current_job.files_failed = failed
    _current_job.files_skipped = skipped
    _current_job.records_indexed = records
    _current_job.warnings = warnings
    _current_job.errors = errors
    _current_job.bytes_total = total_bytes
    _current_job.bytes_processed = min(processed_bytes, total_bytes) if total_bytes else processed_bytes
    _current_job.current_file_bytes = current_file_bytes
    _current_job.current_file_size = current_file_size
    _current_job.current_line = current_line
    _current_job.progress_percent = round(fraction * 100, 2)
    _current_job.lines_per_sec = records / elapsed
    _current_job.mb_per_sec = (processed_bytes / (1024 * 1024)) / elapsed
    _current_job.elapsed_secs = elapsed
    _current_job.eta_secs = (elapsed / fraction) * (1 - fraction) if fraction > 0 else None


async def _is_file_unchanged(db: Database, item: ScannedFile, source_id: int) -> bool:
    row = await db.fetchone(
        "SELECT mtime, size_bytes, status FROM files WHERE source_id=? AND path=?",
        (source_id, str(item.path)),
    )
    return bool(
        row
        and row["status"] == "indexed"
        and row["mtime"] == item.mtime
        and row["size_bytes"] == item.size_bytes
    )


async def _index_file(
    state: AppState,
    job_id: int,
    source_id: int,
    item: ScannedFile,
    batch_size: int,
    progress: ProgressCallback | None = None,
) -> FileIndexResult:
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
    truncated_lines = 0
    batch = []
    max_chars = state.config.indexing.max_line_length
    # UTF-8 needs at most four bytes per character. Never allocate an unlimited line.
    max_raw_bytes = max(4096, max_chars * 4)
    report_every_bytes = 4 * 1024 * 1024
    last_report_bytes = 0
    last_report_at = time.monotonic()

    with open(path, "rb") as handle:
        while True:
            line_start = handle.tell()
            first = handle.readline(max_raw_bytes + 1)
            if not first:
                break

            line_count += 1
            consumed = len(first)
            raw = first[:max_raw_bytes]
            oversized = len(first) > max_raw_bytes

            if oversized and not first.endswith(b"\n"):
                while True:
                    tail = handle.readline(1024 * 1024)
                    if not tail:
                        break
                    consumed += len(tail)
                    if progress and handle.tell() - last_report_bytes >= report_every_bytes:
                        await progress(handle.tell(), records_indexed, line_count)
                        last_report_bytes = handle.tell()
                        last_report_at = time.monotonic()
                    await asyncio.sleep(0)
                    if tail.endswith(b"\n"):
                        break

            if oversized:
                truncated_lines += 1

            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if text:
                if len(text) > max_chars:
                    text = text[:max_chars]
                batch.append(
                    parse_line(
                        text,
                        line_count,
                        line_start,
                        fmt,
                        byte_length=min(consumed, max_raw_bytes),
                    )
                )

            now = time.monotonic()
            should_flush = len(batch) >= batch_size
            should_report = (
                handle.tell() - last_report_bytes >= report_every_bytes
                or now - last_report_at >= 0.75
            )
            if should_flush:
                records_indexed += await write_batch(state, batch, source_id, file_id, path, fmt.value)
                batch.clear()
                should_report = True
            if progress and should_report:
                await progress(handle.tell(), records_indexed, line_count)
                last_report_bytes = handle.tell()
                last_report_at = now
            if line_count % 256 == 0:
                await asyncio.sleep(0)

    if batch:
        records_indexed += await write_batch(state, batch, source_id, file_id, path, fmt.value)

    warning_count = 0
    if truncated_lines:
        warning_count = 1
        await state.db.execute(
            """
            INSERT INTO index_errors(job_id, file_path, message, severity)
            VALUES (?, ?, ?, 'warning')
            """,
            (
                job_id,
                str(path),
                f"{truncated_lines} oversized line(s) were safely truncated to {max_chars} characters for indexing",
            ),
        )

    await state.db.execute(
        """
        UPDATE files SET line_count=?, records_indexed=?, last_indexed_at=?, status='indexed'
        WHERE id=?
        """,
        (line_count, records_indexed, dt.datetime.now(dt.timezone.utc).isoformat(), file_id),
    )
    if progress:
        await progress(item.size_bytes, records_indexed, line_count)
    return FileIndexResult(records_indexed=records_indexed, line_count=line_count, warnings=warning_count)
