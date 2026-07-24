from __future__ import annotations

from pathlib import Path

import pytest

from breachelens.config import Config
from breachelens.db import Database
from breachelens.ingest import index_job
from breachelens.ingest.index_job import JobSnapshot, _index_file, _run_job
from breachelens.ingest.scanner import ScannedFile
from breachelens.state import AppState


async def make_state(tmp_path: Path) -> AppState:
    config = Config()
    config.storage.data_dir = tmp_path / "data"
    config.storage.index_dir = tmp_path / "data" / "index"
    config.storage.db_path = tmp_path / "data" / "pharos.db"
    config.indexing.max_line_length = 64
    config.indexing.batch_size = 2
    db = Database(config.storage.db_path)
    await db.connect()
    await db.run_migrations()
    return AppState(config=config, db=db)


@pytest.mark.asyncio
async def test_failed_file_advances_completed_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await make_state(tmp_path)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = source_dir / "broken.txt"
    source_file.write_text("example@example.com:secret\n", encoding="utf-8")

    source_cur = await state.db.execute(
        "INSERT INTO sources(path, allowed_extensions, status) VALUES (?, '.txt', 'pending')",
        (str(source_dir),),
    )
    source_id = int(source_cur.lastrowid)
    job_cur = await state.db.execute(
        "INSERT INTO index_jobs(source_id, status) VALUES (?, 'running')",
        (source_id,),
    )
    job_id = int(job_cur.lastrowid)

    async def fail_index(*args, **kwargs):
        raise RuntimeError("synthetic parser failure")

    monkeypatch.setattr(index_job, "_index_file", fail_index)
    monkeypatch.setattr(
        index_job,
        "_current_job",
        JobSnapshot(job_id=job_id, source_id=source_id, status="running", started_at="now"),
    )

    await _run_job(state, job_id, source_id, str(source_dir), ".txt", force=True)

    row = await state.db.fetchone(
        "SELECT status, files_total, files_processed, files_failed, errors_count FROM index_jobs WHERE id=?",
        (job_id,),
    )
    assert row["status"] == "completed_with_errors"
    assert row["files_total"] == 1
    assert row["files_processed"] == 1
    assert row["files_failed"] == 1
    assert row["errors_count"] == 1
    await state.db.close()


@pytest.mark.asyncio
async def test_oversized_single_line_is_bounded_and_indexed(tmp_path: Path) -> None:
    state = await make_state(tmp_path)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = source_dir / "huge.txt"
    source_file.write_bytes(b"a" * (2 * 1024 * 1024) + b"\n")
    stat = source_file.stat()

    source_cur = await state.db.execute(
        "INSERT INTO sources(path, allowed_extensions, status) VALUES (?, '.txt', 'pending')",
        (str(source_dir),),
    )
    source_id = int(source_cur.lastrowid)
    job_cur = await state.db.execute(
        "INSERT INTO index_jobs(source_id, status) VALUES (?, 'running')",
        (source_id,),
    )
    job_id = int(job_cur.lastrowid)

    item = ScannedFile(
        path=source_file,
        file_name=source_file.name,
        extension="txt",
        size_bytes=stat.st_size,
        mtime=int(stat.st_mtime),
    )
    progress_events: list[tuple[int, int, int]] = []

    async def progress(file_bytes: int, records: int, lines: int) -> None:
        progress_events.append((file_bytes, records, lines))

    result = await _index_file(state, job_id, source_id, item, 2, progress)
    record = await state.db.fetchone(
        "SELECT byte_length, length(searchable_text) AS text_length FROM records WHERE source_id=?",
        (source_id,),
    )
    warning = await state.db.fetchone(
        "SELECT severity, message FROM index_errors WHERE job_id=?",
        (job_id,),
    )

    assert result.records_indexed == 1
    assert result.line_count == 1
    assert result.warnings == 1
    assert record["byte_length"] <= state.config.indexing.max_line_length * 4
    assert record["text_length"] <= state.config.indexing.max_line_length
    assert warning["severity"] == "warning"
    assert "oversized line" in warning["message"]
    assert progress_events
    assert progress_events[-1][0] == stat.st_size
    await state.db.close()
